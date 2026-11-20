#!/usr/bin/env python3
"""Combine GDS-extracted cell devices with OpenRCX interconnect R/C.
Run transistor-level transient tests at 1 MHz with a configurable output load.
"""
import argparse,json,os,pathlib,re,subprocess,hashlib
import numpy as np
p=argparse.ArgumentParser()
p.add_argument('--pdk-root',default=os.environ.get('PDK_ROOT'),required=not bool(os.environ.get('PDK_ROOT')))
p.add_argument('--corner',choices=['tt','ss','ff','sf','fs'],default='tt')
p.add_argument('--rc',choices=['nom','max','min'],default='nom')
p.add_argument('--vdd',type=float,default=1.8)
p.add_argument('--temperature',type=float,default=25)
p.add_argument('--load-pf',type=float,default=0.033442)
p.add_argument('--ideal-wire',action='store_true')
p.add_argument('--prelayout',action='store_true',help='Use the pre-placement synthesis netlist and the matching PDK cell device models')
p.add_argument('--root',default=str(pathlib.Path(__file__).resolve().parents[1]))
a=p.parse_args();root=pathlib.Path(a.root).resolve();pdk=pathlib.Path(a.pdk_root).resolve()/'sky130A'
final=root/'deliverables'
if not final.exists():final=root/'src/runs/signoff_gds/final'
name=f'{a.corner}_{a.rc}_{a.vdd:g}V_{a.temperature:g}C_{a.load_pf:g}pF'
if a.prelayout and a.ideal_wire:raise ValueError('Choose prelayout or routed ideal-wire baseline')
name += '_prelayout_21us' if a.prelayout else ('_ideal_21us' if a.ideal_wire else '_rc_21us')
netlist_path=root/'official_artifacts/GDS_logs/runs/wokwi/06-yosys-synthesis/tt_um_armohamed_tdc12.nl.v' if a.prelayout else next((final/'pnl').glob('*.v'))
devices_path=pdk/'libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice' if a.prelayout else next((final/'spice').glob('*.spice'))
input_paths=[netlist_path,devices_path]+([] if a.prelayout else [next((final/'spef'/a.rc).glob('*.spef'))])
def path_label(f):return str(f.relative_to(root)) if f.is_relative_to(root) else 'PDK/'+str(f.relative_to(pdk))
input_hashes={path_label(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in input_paths}
name += '_r'+input_hashes[path_label(netlist_path)][:8]
out=root/'reports/rc_spice'/name;out.mkdir(parents=True,exist_ok=True)
(out/'input_hashes.json').write_text(json.dumps(input_hashes,indent=2)+'\n')
# Read cell definitions from the transistor extraction of the delivered GDS.
spice=devices_path.read_text()
spice=re.sub(r'\n\+\s*',' ',spice)
subs={}
for m in re.finditer(r'^\.subckt\s+(\S+)\s*([^\n]*)\n(.*?)^\.ends[^\n]*',spice,re.I|re.M|re.S):
 if m[1]!='tt_um_armohamed_tdc12':subs[m[1]]=(m[2].split(),m[0])
# SPEF is the routed wire network; a node denotes a port, cell pin, or wire point.
spef=[] if a.prelayout else next((final/'spef'/a.rc).glob('*.spef')).read_text().splitlines()
if not a.prelayout:assert '*C_UNIT 1 PF' in spef and '*R_UNIT 1 OHM' in spef
names={};pins={};elements=[];section='';dnet='';coupling_seen={};coupling_rows=0;ground_caps=0;nodes={'VGND':'0','VNB':'0','VPWR':'vdd','VPB':'vdd'}
def expand(t):
 m=re.fullmatch(r'\*(\d+)(:.*)?',t)
 return names[m[1]]+(m[2] or '') if m else t
def node(t):
 t=re.sub(r'\s+','',expand(t).lstrip('\\'))
 if t in ["1'b0","1'h0"]:return '0'
 if t in ["1'b1","1'h1"]:return 'vdd'
 if t not in nodes:nodes[t]=f'wire_node_{len(nodes)}'
 return nodes[t]
for line in spef:
 t=line.split()
 if not t:continue
 if t[0]=='*NAME_MAP':section='names';continue
 if t[0]=='*D_NET':dnet=expand(t[1])
 if t[0] in ['*PORTS','*D_NET','*CONN','*CAP','*RES','*END']:
  section=t[0];continue
 if section=='names' and re.fullmatch(r'\*\d+',t[0]):names[t[0][1:]]=t[1]
 elif section=='*CONN' and t[0]=='*I':
  full=expand(t[1]);inst,pin=full.rsplit(':',1);pins[(inst,pin)]=node(full)
 elif section=='*CAP' and t[0].isdigit():
  val=float(t[-1])
  if val<=0:continue
  n1=node(t[1]);n2=node(t[2]) if len(t)==4 else '0'
  if len(t)==4:
   coupling_rows+=1
   key=tuple(sorted((n1,n2)))
   if key in coupling_seen:
    previous=coupling_seen[key]
    assert previous['owner']!=dnet and previous['copies']==1, 'Ambiguous repeated coupling in one net'
    assert previous['value_pf']==val, 'Reciprocal SPEF coupling values disagree'
    previous['copies']+=1
    continue
   coupling_seen[key]={'owner':dnet,'value_pf':val,'copies':1}
  else:ground_caps+=1
  elements.append(('C',n1,n2,val*1e-12))
 elif section=='*RES' and t[0].isdigit():elements.append(('R',node(t[1]),node(t[2]),max(float(t[3]),1e-6)))
# OpenRCX writes every coupling at full value under both connected D_NETs.
# Instantiate one physical capacitor, retaining both SPEF entries as a check.
assert all(x['copies']==2 for x in coupling_seen.values()), 'Full SPEF must contain reciprocal couplings'
spef_stats={'source_positive_coupling_rows':coupling_rows,'unique_physical_couplings':len(coupling_seen),
 'reciprocal_rows_skipped':coupling_rows-len(coupling_seen),'ground_capacitors':ground_caps,
 'resistors':sum(x[0]=='R' for x in elements),
 'unique_coupling_pf_sum':sum(x['value_pf'] for x in coupling_seen.values())}
(out/'spef_conversion.json').write_text(json.dumps(spef_stats,indent=2)+'\n')
# Instantiate exactly the routed logical cells, with extracted pin positions.
verilog=netlist_path.read_text();insts=[];ignored=[]
for m in re.finditer(r'\b(sky130_\w+)\s+(\\\S+|\w+)\s*\((.*?)\);',verilog,re.S):
 cell,inst,ports=m[1],m[2].lstrip('\\'),dict(re.findall(r'\.(\w+)\s*\(\s*([^)]*?)\s*\)',m[3]))
 if cell not in subs:
  if re.search(r'__(fill|tapvpwrvgnd)_',cell):ignored.append((cell,inst));continue
  raise ValueError('Missing GDS-extracted device definition: '+cell)
 order=subs[cell][0]
 if set(order).issubset({'VPWR','VGND','VPB','VNB'}):
  ignored.append((cell,inst));continue
 if not re.search(r'(?im)^[XMR]\S*\s+',subs[cell][1]):
  raise RuntimeError('Active standard cell is an empty/black-box model: '+cell)
 con=[]
 for pin in order:
  if (inst,pin) in pins:con.append(pins[(inst,pin)])
  elif pin in ports and ports[pin]:con.append(node(ports[pin].strip()))
  elif pin in ['VPWR','VPB','VGND','VNB']:con.append(node(pin))
  else:con.append(node(inst+':NC_'+pin))
 insts.append('Xcell'+str(len(insts))+' '+' '.join(con)+' '+cell)
# Revised TDC stimulus follows.
top='tt_um_armohamed_tdc12'
pulses=[(4.25,6.25),(8.25,11.25),(13.25,17.25)]
stop=21e-6
def pwl_source(label,port,points):
 return 'V'+label+' '+node(port)+' 0 PWL('+ ' '.join(f'{t:.12g} {v*a.vdd:.9g}' for t,v in points)+')'
def pulse_points():
 pts=[(0,0)]
 for lo,hi in pulses:
  for t,value in [(lo*1e-6-.5e-9,0),(lo*1e-6+.5e-9,1),(hi*1e-6-.5e-9,1),(hi*1e-6+.5e-9,0)]:pts.append((t,value))
 return pts+[(stop,0)]
outputs=[node(f'uo_out[{i}]') for i in range(8)]+[node(f'uio_out[{i}]') for i in range(8)]+[node(f'uio_oe[{i}]') for i in range(8)]
sources=[pwl_source('reset','rst_n',[(0,0),(1.7995e-6,0),(1.8005e-6,1),(stop,1)]),
         pwl_source('select','ena',[(0,1),(stop,1)]),pwl_source('pulse','ui_in[0]',pulse_points()),
         f'Vclock {node("clk")} 0 PULSE(0 {a.vdd} 499.5n 1n 1n 499n 1u)']
loads=[f'Cload{i} {n} 0 {a.load_pf:g}p' for i,n in enumerate(outputs)]
# The comparison keeps the same physical devices and external loads. It contracts
# only intercell wire resistors and removes only extracted intercell wire caps.
parents={}
def find(x):
 if parents.get(x,x)!=x:parents[x]=find(parents[x])
 return parents.get(x,x)
if a.ideal_wire:
 for kind,n1,n2,val in elements:
  if kind=='R':parents[find(n2)]=find(n1)
 def rename(s):return re.sub(r'\bwire_node_\d+\b',lambda m:find(m[0]),s)
 insts=[rename(s) for s in insts];sources=[rename(s) for s in sources]
 loads=[rename(s) for s in loads];outputs=[find(n) for n in outputs]
 clock_node=find(node('clk'));pulse_node=find(node('ui_in[0]'))
 wires=[]
else:
 clock_node=node('clk');pulse_node=node('ui_in[0]')
 wires=[f'{kind}wire{i} {n1} {n2} {val:.12g}' for i,(kind,n1,n2,val) in enumerate(elements)]
lines=['* SKY130 TDC GDS devices and routed interconnect',
 f'.lib "{pdk}/libs.tech/ngspice/sky130.lib.spice" {a.corner}',f'.temp {a.temperature}',
 '.option scale=1u method=gear reltol=1e-4 abstol=1e-12 vntol=1e-6',f'VDD vdd 0 {a.vdd}']
lines.extend(v[1] for v in subs.values());lines.extend(insts)
lines.extend(wires);lines.extend(sources);lines.extend(loads)
vecs=['v('+n+')' for n in outputs]+['v('+clock_node+')','v('+pulse_node+')','v('+node('rst_n')+')','v('+node('ena')+')','i(VDD)']
lines.extend(['.save '+' '.join(vecs),'.control','set wr_vecnames','set wr_singlescale',
 'tran 2n 21u 0 20n uic','wrdata transient.tsv '+' '.join(vecs),'quit','.endc','.end'])
deck=out/'tdc.cir';deck.write_text('\n'.join(lines)+'\n')
(out/'.spiceinit').write_text('set ngbehavior=hsa\nset skywaterpdk\nset ng_nomodcheck\noption klu\n')
(out/'node_map.json').write_text(json.dumps(nodes,indent=2))
print('Starting',name,'cells',len(insts),'wire elements',len(wires),flush=True)
r=subprocess.run(['ngspice','-b','-o','ngspice.log','tdc.cir'],cwd=out,timeout=600)
if r.returncode or not (out/'transient.tsv').exists():raise RuntimeError('SPICE failed: '+str(out/'ngspice.log'))
data=np.loadtxt(out/'transient.tsv',skiprows=1);time=data[:,0]
held=0;raw=0;last=0;history=[0,0];publish=-1;pending=0;samples=[];errors=[];delay_ns=[]
last_value=None
for k in range(21):
 edge=(k+.5)*1e-6
 level=int(any(lo*1e-6<edge<hi*1e-6 for lo,hi in pulses))
 active=int(edge>=1.8e-6)
 valid=0
 if not active:
  held=0;raw=0;last=0;history=[0,0];busy=0;publish=-1
 else:
  busy=history[1];history=[level,history[0]]
  if level:raw+=1
  elif last:pending=raw;raw=0;publish=k+2
  last=level
  if k==publish:held=pending;valid=1
 value=held|(valid<<12)|(busy<<13)|(127<<16)
 row=data[np.argmin(abs(time-(edge+200e-9)))];bits=row[1:25]
 got=sum(int(v>a.vdd/2)<<j for j,v in enumerate(bits))
 margin=min(v/a.vdd if (value>>j)&1 else 1-v/a.vdd for j,v in enumerate(bits))
 rec={'cycle':k,'expected_code':held,'observed_code':got&4095,'expected_valid':valid,
      'observed_valid':(got>>12)&1,'expected_busy':busy,'observed_busy':(got>>13)&1,
      'observed_overflow':(got>>14)&1,'observed_unused_out':(got>>15)&1,
      'observed_uio_oe':(got>>16)&255,'minimum_rail_margin':float(margin)}
 samples.append(rec)
 if got!=value or margin<.7:errors.append(rec)
 if last_value is not None:
  for j in range(24):
   old=(last_value>>j)&1;new=(value>>j)&1
   if old==new:continue
   ids=np.where((time>=edge)&(time<=edge+200e-9))[0]
   y=data[ids,1+j]/a.vdd
   crossings=np.where((y[:-1]<.5)&(y[1:]>=.5))[0] if new else np.where((y[:-1]>.5)&(y[1:]<=.5))[0]
   if len(crossings):
    m=ids[crossings[0]];v0=data[m,1+j]/a.vdd;v1=data[m+1,1+j]/a.vdd
    cross=time[m]+(.5-v0)/(v1-v0)*(time[m+1]-time[m])
    delay_ns.append(float((cross-edge)*1e9))
 last_value=value
summary={'case':name,'passed':not errors,'samples_checked':len(samples),
 'conversions_checked':sum(s['expected_valid'] for s in samples),'corner':a.corner,
 'rc':a.rc,'vdd_v':a.vdd,'temperature_c':a.temperature,'load_pf_per_output':a.load_pf,
 'wire_rc_included':not (a.ideal_wire or a.prelayout),'stage':'prelayout' if a.prelayout else ('routed_ideal_wire' if a.ideal_wire else 'extracted'),'signal_cells':len(insts),
 'power_only_or_empty_cells_omitted':len(ignored),'ideal_supply':True,
 'wire_elements':len(wires),'worst_observed_output_delay_ns':max(delay_ns,default=None),
 'scope':('Pre-placement synthesis netlist with PDK transistor cell models' if a.prelayout else 'Actual GDS MOS geometry and cell metal capacitances plus OpenRCX intercell RC')+'; all 24 wrapper outputs; ideal supply; intracell wire resistance not extracted; user tile only',
 'samples':samples,'errors':errors}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k not in ('samples','errors')},indent=2))
if errors:raise SystemExit('FAIL: analog outputs mismatch reference')
print('PASS: 21 clock samples, three independent conversions, all 24 wrapper output levels checked',flush=True)
