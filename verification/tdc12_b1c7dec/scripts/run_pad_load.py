#!/usr/bin/env python3
"""Representative SKY130 GPIO pad 5 pF stress; not assembled-chip extraction."""
import argparse,concurrent.futures,json,pathlib,re,subprocess,time
import numpy as np
p=argparse.ArgumentParser();p.add_argument('--pdk-root',required=True);p.add_argument('--resume',action='store_true');a=p.parse_args()
root=pathlib.Path(__file__).resolve().parents[1];pdk=pathlib.Path(a.pdk_root).resolve()/'sky130A'
library=pdk/'libs.ref/sky130_fd_io/spice/sky130_fd_io.spice'
text=re.sub(r'\n\+\s*',' ',library.read_text())
m=re.search(r'(?im)^\.subckt\s+sky130_fd_io__top_gpiov2\s+([^\n]+)',text)
pins=m[1].split()
cases=[(process,vcore,vio,temp,mode) for process,vcore,vio,temp in [('tt',1.8,3.3,25),('ss',1.6,3.0,100),('ff',1.95,3.6,-40)] for mode in ['output','bidir']]
def run(case):
 process,vcore,vio,temp,mode=case
 name=f'{process}_{vcore:g}Vcore_{vio:g}Vio_{temp:g}C_{mode}_5pF'
 out=root/'reports/pad_load'/name;out.mkdir(parents=True,exist_ok=True)
 if a.resume and (out/'summary.json').exists():
  previous=json.loads((out/'summary.json').read_text())
  if previous.get('passed'):return previous
 mapping={pin:'pad_'+pin.lower().replace('[','_').replace(']','') for pin in pins}
 for pin in ['VSSA','VSSD','VSSIO','VSSIO_Q','AMUXBUS_A','AMUXBUS_B','ANALOG_EN','ANALOG_POL','ANALOG_SEL','DM[0]','HLD_OVR','IB_MODE_SEL','OE_N','SLOW','VTRIP_SEL']:mapping[pin]='0'
 for pin in ['VCCD','VCCHIB','DM[2]','DM[1]','ENABLE_VDDIO']:mapping[pin]='vcore'
 for pin in ['VDDA','VDDIO','VDDIO_Q','VSWITCH','ENABLE_H','ENABLE_INP_H','ENABLE_VDDA_H','ENABLE_VSWITCH_H','HLD_H_N']:mapping[pin]='vio'
 mapping['INP_DIS']='vcore' if mode=='output' else '0'
 mapping['OUT']='data';mapping['PAD']='pad'
 deck=[f'* Representative pad-only load test, {name}',f'.lib "{pdk}/libs.tech/ngspice/sky130.lib.spice" {process}',f'.include "{library}"',f'.temp {temp}',
 '.option scale=1u method=gear reltol=1e-4 abstol=1e-12 vntol=1e-6',f'Vcore vcore 0 {vcore}',f'Vio vio 0 {vio}',
 f'Vdata data 0 PULSE(0 {vcore} 50n 1n 1n 99n 200n)',
 'Xpad '+' '.join(mapping[pin] for pin in pins)+' sky130_fd_io__top_gpiov2','Cload pad 0 5p',
 '.save v(data) v(pad) i(Vio) i(Vcore)','.control','set wr_vecnames','set wr_singlescale',
 ('tran 0.2n 1.1u 0 1n uic' if process=='tt' and mode=='output' else 'tran 0.2n 1.1u 0 1n'),'wrdata transient.tsv v(data) v(pad) i(Vio) i(Vcore)','quit','.endc','.end']
 (out/'pad.cir').write_text('\n'.join(deck)+'\n')
 (out/'.spiceinit').write_text('set ngbehavior=hsa\nset skywaterpdk\nset ng_nomodcheck\noption klu\n')
 start=time.monotonic()
 r=subprocess.run(['ngspice','-b','-o','ngspice.log','pad.cir'],cwd=out,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT,timeout=180)
 if r.returncode or not (out/'transient.tsv').exists():raise RuntimeError('Pad SPICE failed: '+name)
 d=np.loadtxt(out/'transient.tsv',skiprows=1);errors=[];delays=[];samples=[]
 for k in range(10):
  edge=(50.5+100*k)*1e-9;target=1-k%2
  sample=d[np.argmin(abs(d[:,0]-(edge+45e-9)))];v=float(sample[2]);margin=v/vio if target else 1-v/vio
  record={'edge':k,'expected':target,'pad_voltage_v':v,'rail_margin':margin};samples.append(record)
  if margin<.7:errors.append(record)
  ids=np.where((d[:,0]>=edge)&(d[:,0]<edge+50e-9))[0]; y=d[ids,2]/vio
  crossings=np.where((y[:-1]<.5)&(y[1:]>=.5))[0] if target else np.where((y[:-1]>.5)&(y[1:]<=.5))[0]
  if len(crossings):
   j=ids[crossings[0]];cross=d[j,0]+(.5*vio-d[j,2])/(d[j+1,2]-d[j,2])*(d[j+1,0]-d[j,0]);delays.append(float((cross-edge)*1e9))
 result={'case':name,'passed':not errors and len(delays)==10,'process':process,'vcore_v':vcore,'vio_v':vio,'temperature_c':temp,'mode':mode,'load_pf':5,'clocked_edge_rate_mhz':5,'edges_checked':len(samples),'max_observed_delay_ns':max(delays,default=None),'minimum_sampled_rail_margin':min(x['rail_margin'] for x in samples),'runtime_s':time.monotonic()-start,'samples':samples,'errors':errors,'scope':'PDK schematic GPIO pad model, strong CMOS DM=110, ideal supplies; no shared mux, package/board routing or assembled-chip PEX'}
 (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
 print(name,'PASS' if result['passed'] else 'FAIL',flush=True)
 return result
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:results=list(ex.map(run,cases))
(root/'reports/pad_load/summary.json').write_text(json.dumps(results,indent=2)+'\n')
if not all(r['passed'] for r in results):raise SystemExit('PAD LOAD TEST FAIL')
print('PASS: six representative pad/PVT/mode tests at 5 pF')
