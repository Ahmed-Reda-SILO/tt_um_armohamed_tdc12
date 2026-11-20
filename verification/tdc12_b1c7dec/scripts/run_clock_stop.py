#!/usr/bin/env python3
import argparse,pathlib,subprocess,json
p=argparse.ArgumentParser();p.add_argument('--pdk-root',required=True);a=p.parse_args()
r=pathlib.Path(__file__).resolve().parents[1];pdk=pathlib.Path(a.pdk_root).resolve()/'sky130A'
results=[]
for mode in ['rtl','gate']:
 out=r/'reports'/('clock_stop_'+mode);out.mkdir(exist_ok=True)
 cmd=['iverilog','-g2012','-s','wrapper_clock_stop_tb','-o',str(out/'sim.vvp')]
 if mode=='rtl':cmd += [str(r/'src/project.v'),str(r/'src/pulse_width_tdc.v')]
 else:cmd += ['-DFUNCTIONAL','-DPOWER_PINS','-DUSE_POWER_PINS','-DSIM','-DUNIT_DELAY=#1',str(pdk/'libs.ref/sky130_fd_sc_hd/verilog/primitives.v'),str(pdk/'libs.ref/sky130_fd_sc_hd/verilog/sky130_fd_sc_hd.v'),str(r/'deliverables/pnl/tt_um_armohamed_tdc12.pnl.v')]
 cmd += [str(r/'test/wrapper_clock_stop_tb.sv')]
 subprocess.run(cmd,check=True,capture_output=True,text=True)
 run=subprocess.run(['vvp',str(out/'sim.vvp')],cwd=out,capture_output=True,text=True,timeout=30)
 (out/'simulation.log').write_text(run.stdout+run.stderr)
 result={'mode':mode,'passed':run.returncode==0 and 'PASS:' in run.stdout};results.append(result)
 print(mode,run.stdout.strip())
(r/'reports/clock_stop_summary.json').write_text(json.dumps(results,indent=2)+'\n')
if not all(x['passed'] for x in results):raise SystemExit('Stopped-clock wrapper test failed')
