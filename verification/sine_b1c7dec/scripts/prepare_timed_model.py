#!/usr/bin/env python3
"""Adapt a complete macro netlist to Icarus 12 using real SDF cell/wire delays.

Only the simulation view is changed. GDS, production RTL and cell logic stay
unchanged. Explicit per-sink wires implement SDF INTERCONNECT, which Icarus 12
does not support directly. Real PDK specify I/O paths receive cell SDF delays;
setup/hold/width signoff remains the separate extracted STA check.
"""
import argparse, hashlib, json, re, subprocess
from pathlib import Path

def sexpr(text):
    tokens=re.findall(r'"[^"\\]*(?:\\.[^"\\]*)*"|[()]|[^\s()]+',text)
    stack=[]; result=[]
    for token in tokens:
        if token=='(':
            node=[]
            (stack[-1] if stack else result).append(node); stack.append(node)
        elif token==')':stack.pop()
        else:stack[-1].append(token)
    if stack:raise ValueError('Unbalanced SDF')
    return result[0]
def encode(n):
    return '('+' '.join(encode(x) if isinstance(x,list) else x for x in n)+')'
def walk(n,key):
    if isinstance(n,list):
        if n and n[0]==key:yield n
        for x in n:
            if isinstance(x,list):yield from walk(x,key)
def value(n,choice=1):
    s=n[0] if isinstance(n,list) else n
    a=s.split(':');return float(a[min(choice,len(a)-1)] or a[0])

def build(root,audit,pdk,netlist,sdf,folder,prelayout=False,zero=False):
    folder.mkdir(parents=True,exist_ok=True)
    tree=sexpr(sdf.read_text()); cells=list(walk(tree,'CELL'))
    macro=next(c for c in cells if next(walk(c,'CELLTYPE'))[1].strip('"')=='tt_um_armohamed_tdc12')
    cell_nodes=[c for c in cells if c is not macro]
    inter=list(walk(macro,'INTERCONNECT'))
    source_interconnect_entries=len(inter)
    if prelayout:
        if any(value(x)!=0 for c in inter for x in c[3:]):
            raise RuntimeError('Pre-layout reference unexpectedly has nonzero interconnect delay')
        inter=[]
    cellmap={next(walk(c,'INSTANCE'))[1]:next(walk(c,'CELLTYPE'))[1].strip('"') for c in cell_nodes}
    assert len(cellmap)==len(cell_nodes)
    wiremap={c[2]:c for c in inter}
    if len(wiremap)!=len(inter):raise RuntimeError('Multiple drivers/delays for one SDF sink')
    lib=pdk/'libs.ref/sky130_fd_sc_hd/verilog'
    processed=root/'build/pdk_functional_preprocessed.v'
    if not processed.exists():
        cmd=['iverilog','-E','-g2012','-DFUNCTIONAL','-DPOWER_PINS','-DUSE_POWER_PINS','-DSIM','-DUNIT_DELAY=#0',
             '-o',str(processed),str(lib/'primitives.v'),str(lib/'sky130_fd_sc_hd.v')]
        subprocess.run(cmd,check=True,capture_output=True,text=True)
    libtext=processed.read_text()
    modules={m[1]:m[0] for m in re.finditer(r'\bmodule\s+(\w+)\b.*?\bendmodule\b',libtext,re.S)}
    timingtext=(lib/'sky130_fd_sc_hd.v').read_text()
    timingmodules={}
    for m in re.finditer(r'\bmodule\s+(\w+)\b.*?\bendmodule\b',timingtext,re.S):
        if 'specify' in m[0]:timingmodules[m[1]]=m[0]
    types=set(cellmap.values())
    # Obtain exact port directions from the preprocessed, power-aware PDK model.
    dirs={}
    for kind in types:
        block=modules[kind]
        dirs[kind]={pin:dr for dr,pin in re.findall(r'\b(input|output|inout)\s+(\w+)\s*;',block)}
    # Add ONLY PDK timing paths to the functional cell body. Timing-check delayed
    # data/clock outputs are unsupported in Icarus; STA supplies those checks.
    patched=[]; path_count=0
    for kind in sorted(types):
        functional=modules[kind]
        paths=[]
        if kind in timingmodules:
            spec=timingmodules[kind].split('specify',1)[1].split('endspecify',1)[0]
            spec=re.sub(r'//[^\n]*','',spec)
            paths=[line.strip()+';' for line in spec.split(';') if line.strip() and not line.strip().startswith('$')]
        arcs=sum(1 for c in cell_nodes if next(walk(c,'CELLTYPE'))[1].strip('"')==kind for _ in walk(c,'IOPATH'))
        if arcs and not paths:raise RuntimeError('Missing PDK specify paths: '+kind)
        path_count+=len(paths)
        patched.append(functional.replace('endmodule','\nspecify\n'+'\n'.join(paths)+'\nendspecify\nendmodule'))
    # Primitive definitions are retained with their original zero unit delay.
    primitives='\n'.join(m[0] for m in re.finditer(r'^primitive\s+[^\n]*\(.*?\bendprimitive\b',libtext,re.S|re.M))
    license_header='/* Verification derivative of SkyWater sky130_fd_sc_hd Verilog.\n * Copyright 2020 The SkyWater PDK Authors. SPDX-License-Identifier: Apache-2.0\n * Cell logic unchanged; timing adapter policies are recorded in model_summary.json.\n */\n'
    model=license_header+'`timescale 1ns/1fs\n'+primitives+'\n'+'\n'.join(patched)+'\n'
    (folder/'cells.v').write_text(model)
    text=netlist.read_text()
    text=re.sub(r'`timescale[^\n]*','',text)
    if prelayout:
        # Original synthesis netlist has no power ports. Add only ideal power
        # connections so the matching power-aware PDK model can be used.
        m=re.search(r'\bmodule\s+tt_um_armohamed_tdc12\s*\((.*?)\);',text,re.S)
        text=text[:m.start()]+m[0].replace(');',', VPWR, VGND);\ninout VPWR, VGND;')+text[m.end():]
    wires=[]; assignments=[]; used=set(); omitted=[]; kept=[]
    def adapt(m):
        kind,inst,body=m[1],m[2].lstrip('\\'),m[3]
        ports=dict(re.findall(r'\.(\w+)\s*\(\s*([^)]*?)\s*\)',body))
        if inst not in cellmap:
            if set(ports).issubset({'VPWR','VGND','VPB','VNB'}) or (kind.endswith('__conb_1')):
                # Constant-output cells need their functional model, even when
                # there are no SDF timing arcs.
                if not set(ports).issubset({'VPWR','VGND','VPB','VNB'}):
                    if kind not in types:
                        types.add(kind);patched.append(modules[kind])
                    if prelayout:
                        for pin,n in [('VPWR','VPWR'),('VPB','VPWR'),('VGND','VGND'),('VNB','VGND')]:
                            if pin not in ports:ports[pin]=n
                    kept.append(inst)
                    return kind+' '+m[2]+' ('+', '.join('.'+pin+'('+net+' )' for pin,net in ports.items())+');'
                omitted.append(inst);return ''
            raise RuntimeError('Active instance absent from SDF: '+inst+' '+kind)
        assert kind==cellmap[inst],(kind,cellmap[inst])
        kept.append(inst)
        if prelayout:
            for pin,n in [('VPWR','VPWR'),('VPB','VPWR'),('VGND','VGND'),('VNB','VGND')]:
                if pin not in ports:ports[pin]=n
        for pin,net in list(ports.items()):
            sink=inst+'/'+pin
            if dirs[kind].get(pin)=='input' and pin not in ['VPWR','VGND','VPB','VNB'] and sink in wiremap:
                c=wiremap[sink];used.add(sink);name='audit_wire_'+str(len(wires));wires.append(name)
                delays=[value(x) for x in c[3:]];dr,df=(delays*2)[:2]
                if zero:dr=df=0
                assignments.append(f'assign #({dr:.9f}, {df:.9f}) {name} = {net} ;')
                ports[pin]=name
        return kind+' '+m[2]+' ('+', '.join('.'+pin+'('+net+' )' for pin,net in ports.items())+');'
    text=re.sub(r'\b(sky130_\w+)\s+(\\\S+|\w+)\s*\((.*?)\);',adapt,text,flags=re.S)
    # Output-port wire delays are also preserved. The replacement touches only
    # bit references in the body, not vector port declarations.
    for c in inter:
        sink=c[2]
        if sink in used:continue
        if re.fullmatch(r'(uo_out|uio_out|uio_oe)\[[0-7]\]',sink):
            name='audit_out_'+re.sub(r'\W','_',sink);wires.append(name)
            text=re.sub(r'\b'+re.escape(sink),name,text)
            delays=[value(x) for x in c[3:]];dr,df=(delays*2)[:2]
            if zero:dr=df=0
            assignments.append(f'assign #({dr:.9f}, {df:.9f}) {sink} = {name};');used.add(sink)
        else:raise RuntimeError('Unmapped SDF interconnect: '+str(c))
    assert used==set(wiremap)
    text=text.replace('endmodule','\n'+''.join('wire '+w+';\n' for w in wires)+'\n'+'\n'.join(assignments)+'\nendmodule')
    (folder/'macro.v').write_text('`timescale 1ns/1fs\n'+text)
    # Any newly retained tie cell gets its unchanged PDK functional model.
    model=license_header+'`timescale 1ns/1fs\n'+primitives+'\n'+'\n'.join(patched)+'\n'
    (folder/'cells.v').write_text(model)
    def filtered(n):
        result=[]
        for x in n:
            if isinstance(x,list) and x and x[0] in ['INTERCONNECT','TIMINGCHECK']:continue
            if isinstance(x,list):x=filtered(x)
            result.append(x)
        return result
    cf=filtered(tree)
    cf=[x for x in cf if not (isinstance(x,list) and x and x[0]=='CELL' and next(walk(x,'CELLTYPE'))[1].strip('"')=='tt_um_armohamed_tdc12')]
    # OpenSTA can emit two unconditional IOPATH records for the same pins of
    # non-unate logic. A last-record-wins import loses one polarity's delay.
    # Use the conservative per-transition envelope and apply it to every PDK
    # conditional path for those pins. Preserve this as an explicit limitation.
    ambiguous=0;negative_values=0
    for absolute in walk(cf,'ABSOLUTE'):
        groups={};other=[]
        for entry in absolute[1:]:
            if isinstance(entry,list) and entry[0]=='IOPATH':groups.setdefault((entry[1],entry[2]),[]).append(entry)
            else:other.append(entry)
        normalized=[]
        for key,arcs in groups.items():
            if len(arcs)>1:ambiguous+=1
            n=arcs[0][:3]
            for j in range(3,len(arcs[0])):
                triple=[max(value(arc[j],k) for arc in arcs) for k in range(3)]
                negative_values+=sum(v<0 for v in triple)
                triple=[max(0,v) for v in triple]
                n.append([':'.join(f'{v:.9f}' for v in triple)])
            normalized.append(n)
        absolute[:]=['ABSOLUTE',*other,*normalized]
    if zero:
        for arc in walk(cf,'IOPATH'):
            for i,x in enumerate(arc):
                if isinstance(x,list) and x and ':' in str(x[0]):arc[i]=['0:0:0']
    (folder/'cells.sdf').write_text(encode(cf).replace(' (CELL ', '\n (CELL ')+'\n')
    metadata={'netlist':str(netlist),'sdf':str(sdf),'netlist_sha256':hashlib.sha256(netlist.read_bytes()).hexdigest(),
        'sdf_sha256':hashlib.sha256(sdf.read_bytes()).hexdigest(),'signal_instances':len(kept),'timed_instances':len(cellmap),
        'cell_iopath_entries':sum(1 for c in cell_nodes for _ in walk(c,'IOPATH')),'source_interconnect_entries':source_interconnect_entries,'interconnect_entries':len(inter),
        'interconnect_entries_mapped':len(used),'omitted_power_only_cells':len(omitted),'zero_delay_control':zero,
        'cell_paths':'SDF backannotated onto original PDK specify I/O paths with unchanged PDK functional cell logic',
        'normalized_cell_iopaths':sum(1 for _ in walk(cf,'IOPATH')),'ambiguous_arc_groups':ambiguous,
        'ambiguous_arc_policy':'Per-transition maximum envelope for duplicate unconditional input/output SDF arcs; all PDK conditional paths receive this envelope',
        'negative_cell_transition_values_clamped':negative_values,
        'negative_delay_policy':'Negative characterized cell delays clamped to zero for causal event simulation; original values remain in separate STA signoff',
        'wire_paths':'Explicit per-sink SDF rise/fall continuous-assignment delays',
        'timing_checks':'setup/hold/width checked separately by STA; no notifier or metastability simulation'}
    (folder/'model_summary.json').write_text(json.dumps(metadata,indent=2)+'\n')
    return metadata

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--audit-root',type=Path,required=True);p.add_argument('--pdk-root',type=Path,required=True)
    p.add_argument('--sdf',type=Path,required=True);p.add_argument('--netlist',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--prelayout',action='store_true');p.add_argument('--zero',action='store_true');a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    print(json.dumps(build(root,a.audit_root.resolve(),a.pdk_root.resolve()/'sky130A',a.netlist.resolve(),a.sdf.resolve(),a.output.resolve(),a.prelayout,a.zero),indent=2))
