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
p.add_argument('--case',choices=['a','b'],required=True)
p.add_argument('--out-root',default=str(pathlib.Path(__file__).resolve().parents[1]/'runs'))
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
out=pathlib.Path(a.out_root).resolve()/('pre' if a.prelayout else 'post')/a.case;out.mkdir(parents=True,exist_ok=True)
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


# Test A uses three independent widths. Test B uses the exact existing guarded
# PWM stimulus so transistor and timed gate-level records can be compared.
if a.case=='a':
 records=[{'sample':i,'start_ns':int(lo*1000),'width_ns':int(w*1000),
           'ideal_width_ns':w*1000,'phase_guard_ns':0,'expected_code':int(w),
           'expected_overflow':0,'sine_normalized':None}
          for i,(lo,w) in enumerate([(8.25,5),(23.25,10),(43.25,20)])]
 stop_ns=75000
else:
 stim=json.loads((pathlib.Path(__file__).resolve().parent/'pwm_1khz.json').read_text())
 records=stim['pulses'];stop_ns=stim['finish_ns']
stop=stop_ns*1e-9
pulses=[(x['start_ns']*1e-9,(x['start_ns']+x['width_ns'])*1e-9) for x in records]
(out/'stimulus.json').write_text(json.dumps({'case':a.case,'finish_ns':stop_ns,'pulses':records},indent=2)+'\n')
# Independently derive expected counts from reference sampling instants.
clock_edges=np.arange(.5e-6,stop,1e-6)
for rec,(lo,hi) in zip(records,pulses):
 observed_samples=int(np.count_nonzero((clock_edges>lo)&(clock_edges<hi)))
 assert observed_samples==rec['expected_code'],(rec,observed_samples)
def pwl_source(label,port,points):
 return 'V'+label+' '+node(port)+' 0 PWL('+ ' '.join(f'{t:.15g} {v*a.vdd:.12g}' for t,v in points)+')'
pts=[(0,0)]
for lo,hi in pulses:
 pts.extend([(lo-.5e-9,0),(lo+.5e-9,1),(hi-.5e-9,1),(hi+.5e-9,0)])
pts.append((stop,0))
outputs=[node(f'uo_out[{i}]') for i in range(8)]+[node(f'uio_out[{i}]') for i in range(8)]+[node(f'uio_oe[{i}]') for i in range(8)]
sources=[pwl_source('reset','rst_n',[(0,0),(3.9995e-6,0),(4.0005e-6,1),(stop,1)]),
 pwl_source('select','ena',[(0,1),(stop,1)]),pwl_source('pulse','ui_in[0]',pts),
 f'Vclock {node("clk")} 0 PULSE(0 {a.vdd} 499.5n 1n 1n 499n 1u)']
unused=[f'ui_in[{i}]' for i in range(1,8)]+[f'uio_in[{i}]' for i in range(8)]
sources += [f'Vunused{i} {node(n)} 0 0' for i,n in enumerate(unused)]
loads=[f'Cload{i} {n} 0 {a.load_pf:g}p' for i,n in enumerate(outputs)]
wires=[f'{kind}wire{i} {n1} {n2} {val:.15g}' for i,(kind,n1,n2,val) in enumerate(elements)]
assert not a.ideal_wire,'No ideal wire substitution is permitted for the extracted comparison'
lines=['* TDC12 academic report matched continuous BSIM test '+a.case,
 f'.lib "{pdk}/libs.tech/ngspice/sky130.lib.spice" {a.corner}',f'.temp {a.temperature}',
 '.option scale=1u method=gear reltol=1e-4 abstol=1e-12 vntol=1e-6',f'VDD vdd 0 {a.vdd}','Vbench_ground ground_probe 0 0']
lines.extend(v[1] for v in subs.values())
lines.extend(insts);lines.extend(wires);lines.extend(sources);lines.extend(loads)
vecs=['v('+n+')' for n in outputs]+['v('+node('clk')+')','v('+node('ui_in[0]')+')','v('+node('rst_n')+')','v('+node('ena')+')','i(VDD)']
vecs += ['v('+node(n)+')' for n in unused]+['v(vdd)','v(ground_probe)']
columns=['time_s']+[f'uo_out[{i}]_V' for i in range(8)]+[f'uio_out[{i}]_V' for i in range(8)]+[f'uio_oe[{i}]_V' for i in range(8)]
columns += ['clk_V','ui_in[0]_V','rst_n_V','ena_V','i_VDD_A']+[n+'_V' for n in unused]+['VPWR_V','VGND_V']
(out/'columns.json').write_text(json.dumps(columns,indent=2)+'\n')
lines.extend(['.save '+' '.join(vecs),'.control','set wr_vecnames','set wr_singlescale','set numdgt=15',
 'set num_threads=2',f'tran 2n {stop:.15g} 0 20n uic','wrdata transient.tsv '+' '.join(vecs),
 'echo COMPLETE_CONTINUOUS_BSIM_REPORT_TEST','rusage','quit','.endc','.end'])
(out/'tdc.cir').write_text('\n'.join(lines)+'\n')
(out/'.spiceinit').write_text('set ngbehavior=hsa\nset skywaterpdk\nset ng_nomodcheck\noption klu\n')
(out/'node_map.json').write_text(json.dumps(nodes,indent=2)+'\n')
import time as timer
start=timer.monotonic()
print(f'Starting continuous {stop_ns/1000:g} us BSIM stage={"pre" if a.prelayout else "post"} case={a.case}, {len(insts)} active cells, {len(wires)} intercell RC elements',flush=True)
with (out/'launcher.log').open('w') as log:
 r=subprocess.run(['ngspice','-b','-o','ngspice.log','tdc.cir'],cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=18000)
wall=timer.monotonic()-start
assert r.returncode==0 and 'COMPLETE_CONTINUOUS_BSIM_REPORT_TEST' in (out/'ngspice.log').read_text(),'Incomplete transistor transient'
data=np.loadtxt(out/'transient.tsv',skiprows=1)
assert data.shape[1]==len(columns),(data.shape,len(columns))
t=data[:,0];assert t[-1]>=stop-1e-12
np.savez_compressed(out/'waveforms.npz',data=data)
def sample(when):return np.array([np.interp(when,t,data[:,j]) for j in range(1,25)])
def packed(when):return sum(int(v>a.vdd/2)<<j for j,v in enumerate(sample(when)))
def crossing(col,rise):
 y=data[:,col]-a.vdd/2
 ids=np.where(((y[:-1]<0)&(y[1:]>=0)) if rise else ((y[:-1]>0)&(y[1:]<=0)))[0]
 return [float(t[i]-y[i]*(t[i+1]-t[i])/(y[i+1]-y[i])) for i in ids if t[i]>4e-6]
checks=[];errors=[];held=0;raw=0;last=0;hist=[0,0];publish=-1;pending=0
for k,edge in enumerate(clock_edges):
 level=int(any(lo<edge<hi for lo,hi in pulses));valid=0
 if edge<4e-6:
  held=0;raw=0;last=0;hist=[0,0];publish=-1;pending=0;busy=0
 else:
  busy=hist[1];hist=[level,hist[0]]
  if level:raw+=1
  elif last:pending=raw;raw=0;publish=k+2
  last=level
  if k==publish:held=pending;valid=1
 expect=held|(valid<<12)|(busy<<13)|(127<<16)
 when=edge+200e-9;got=packed(when);v=sample(when)
 margin=float(min(x/a.vdd if (expect>>j)&1 else 1-x/a.vdd for j,x in enumerate(v)))
 rec={'cycle':k,'time_us':when*1e6,'expected_packed':expect,'observed_packed':got,
      'expected_code':held,'observed_code':got&4095,
      'expected_valid':valid,'observed_valid':(got>>12)&1,'expected_busy':busy,'observed_busy':(got>>13)&1,
      'observed_overflow':(got>>14)&1,'observed_uio_oe':(got>>16)&255,'rail_margin':margin}
 checks.append(rec)
 if got!=expect or margin<.7:errors.append(rec)
vr=crossing(13,True);vf=crossing(13,False);cr=crossing(25,True);ir=crossing(26,True);iff=crossing(26,False)
assert len(vr)==len(vf)==len(ir)==len(iff)==len(records),(len(vr),len(vf),len(ir),len(iff),len(records))
conversions=[]
for i,(rise,fall,stim) in enumerate(zip(vr,vf,records)):
 want=stim['expected_code'];clock=next(x for x in cr if x>rise+1e-9)
 cap=packed(clock-.1e-9);when=pulses[i][1]+5e-6;read=packed(when)
 rec={'conversion':i+1,'expected_code':want,'captured_code':cap&4095,'capture_valid':(cap>>12)&1,
      'capture_clock_us':clock*1e6,'overflow':(cap>>14)&1,'valid_rise_us':rise*1e6,
      'valid_fall_us':fall*1e6,'valid_width_us':(fall-rise)*1e6,'input_rise_us':ir[i]*1e6,
      'input_fall_us':iff[i]*1e6,'input_width_us':(iff[i]-ir[i])*1e6,
      'fall_to_valid_ns':(rise-iff[i])*1e9,'width_error_us':(cap&4095)-(iff[i]-ir[i])*1e6,
      'ideal_width_us':stim['ideal_width_ns']/1000,'phase_guard_ns':stim['phase_guard_ns'],
      'sine_normalized':stim.get('sine_normalized'),
      'read_5us_time_us':when*1e6,'read_5us_code':read&4095,'read_5us_valid':(read>>12)&1,
      'read_5us_busy':(read>>13)&1,'read_5us_overflow':(read>>14)&1,
      'read_uo_hex':f'0x{read&255:02X}','read_uio_hex':f'0x{(read>>8)&255:02X}'}
 rec['passed']=(rec['captured_code']==rec['read_5us_code']==want and rec['capture_valid']==1 and
                rec['overflow']==rec['read_5us_overflow']==rec['read_5us_busy']==rec['read_5us_valid']==0 and
                abs(rec['valid_width_us']-1)<.01)
 conversions.append(rec)
# Edge rates from actual analog output nodes, excluding ideal source/tie ports.
edge_rates=[]
for col in range(1,17):
 y=data[:,col]/a.vdd
 for rising in [True,False]:
  ys=y if rising else 1-y
  ids=np.where((ys[:-1]<.5)&(ys[1:]>=.5)&(t[:-1]>8e-6))[0]
  for idx in ids:
   begin=max(0,idx-50);end=min(len(t)-1,idx+50)
   ia=np.where((ys[begin:idx+1]<.1)&(ys[begin+1:idx+2]>=.1))[0]
   ib=np.where((ys[idx:end]<.9)&(ys[idx+1:end+1]>=.9))[0]
   if not len(ia) or not len(ib):continue
   ka=begin+ia[-1];kb=idx+ib[0]
   ta=t[ka]+(.1-ys[ka])*(t[ka+1]-t[ka])/(ys[ka+1]-ys[ka])
   tb=t[kb]+(.9-ys[kb])*(t[kb+1]-t[kb])/(ys[kb+1]-ys[kb])
   edge_rates.append({'port':columns[col][:-2],'edge':'rise' if rising else 'fall','time_us':t[idx]*1e6,'t10_90_ns':float((tb-ta)*1e9)})
# Supply current is active-macro model current under ideal rails, not board power.
start_power=8.25e-6;end_power=2008.25e-6 if a.case=='b' else 73.25e-6
ix=(t>=start_power)&(t<=end_power)
power=-a.vdd*data[:,29]
energy=float(np.trapezoid(power[ix],t[ix]))
avg=energy/float(t[ix][-1]-t[ix][0])
import csv
for filename,rows in [('clock_samples.csv',checks),('conversions.csv',conversions),('edge_rates.csv',edge_rates)]:
 if rows:
  with (out/filename).open('w') as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
summary={'stage':'pre' if a.prelayout else 'post','case':a.case,
 'passed':not errors and all(x['passed'] for x in conversions),
 'source_commit':'b1c7dec19f113eb7fe47a1986d12d9c465be0c28',
 'gds_sha256':'2c66650721f9d8c3d54b18e39038064a20b95f048d1b69d987ed50766105bd40',
 'clock_hz':1000000,'corner':a.corner,'vdd_v':a.vdd,'temperature_c':a.temperature,
 'tstep_ns':2,'max_timestep_ns':20,'continuous_transient_us':float(t[-1]*1e6),'pause_resume_used':False,
 'active_cells':len(insts),'rc_elements':len(wires),'spef_conversion':spef_stats,'omitted_power_only_cells':len(ignored),
 'load_pf_per_output':a.load_pf,'checked_clock_samples':len(checks),'wrapper_outputs_checked':24,
 'conversions':conversions,'errors':errors,'analog_rows':len(data),'wall_seconds':wall,
 'active_macro_average_supply_power_uW':avg*1e6,'active_macro_energy_pJ':energy*1e12,
 'power_window_us':[start_power*1e6,end_power*1e6],
 'fall_to_valid_ns_range':[min(x['fall_to_valid_ns'] for x in conversions),max(x['fall_to_valid_ns'] for x in conversions)],
 'valid_width_us_range':[min(x['valid_width_us'] for x in conversions),max(x['valid_width_us'] for x in conversions)],
 'max_abs_width_error_us':max(abs(x['width_error_us']) for x in conversions),
 'output_rise_10_90_ns_range':([min(x['t10_90_ns'] for x in edge_rates if x['edge']=='rise'),max(x['t10_90_ns'] for x in edge_rates if x['edge']=='rise')] if edge_rates else None),
 'output_fall_90_10_ns_range':([min(x['t10_90_ns'] for x in edge_rates if x['edge']=='fall'),max(x['t10_90_ns'] for x in edge_rates if x['edge']=='fall')] if edge_rates else None),
 'minimum_settled_rail_margin':min(x['rail_margin'] for x in checks),
 'input_hashes':input_hashes,'deck_sha256':hashlib.sha256((out/'tdc.cir').read_bytes()).hexdigest(),
 'scope':'Continuous BSIM of full active user macro and wrapper; ideal rails; extracted GDS MOS geometry and cell metal capacitance plus OpenRCX intercell R/C after layout. Power-only cells, intracell wire resistance, shared shuttle mux, pads, package and PCB are excluded.'}
if a.case=='b':
 err=np.array([(x['captured_code']-25)/20-x['sine_normalized'] for x in conversions])
 summary['decoded_sine_normalized_rmse']=float(np.sqrt(np.mean(err**2)))
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k not in ['errors','conversions']},indent=2),flush=True)
if not summary['passed']:raise SystemExit('Measured continuous BSIM waveform checks failed; inspect preserved data')

