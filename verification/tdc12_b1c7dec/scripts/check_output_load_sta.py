#!/usr/bin/env python3
"""Check characterized cell electrical limits at actual TDC port loads."""
from pathlib import Path
import argparse,concurrent.futures,json,os,re,subprocess
p=argparse.ArgumentParser();p.add_argument('--pdk-root',default=os.environ.get('PDK_ROOT'),required=not bool(os.environ.get('PDK_ROOT')));p.add_argument('--state',help='Compatible imported database and exact SPEF/SDC paths');a=p.parse_args()
root=Path(__file__).resolve().parents[1];pd=Path(a.pdk_root).resolve()/'sky130A';base=root/'reports/before_after/load_sta';base.mkdir(parents=True,exist_ok=True)
ports=' '.join([f'uo_out[{i}]' for i in range(8)]+[f'uio_out[{i}]' for i in range(7)])
corners=[('nom','tt_025C_1v80'),('max','ss_100C_1v60'),('min','ff_n40C_1v95')]
state=json.loads(Path(a.state).read_text()) if a.state else None
def run(case):
 load,rc,libcase=case;name=f'{load}pF_{rc}_{libcase}';out=base/name;out.mkdir(exist_ok=True)
 final=root/'deliverables';spef=state['spef'][rc+'_*'] if state else next((final/'spef'/rc).glob('*.spef'))
 odb=state['odb'] if state else next((final/'odb').glob('*.odb'))
 sdc=state['sdc'] if state else next((final/'sdc').glob('*.sdc'))
 commands=[f'read_liberty {{{pd}/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__{libcase}.lib}}',f'read_db {{{odb}}}',f'read_sdc {{{sdc}}}',f'read_spef {{{spef}}}', 'set_propagated_clock [all_clocks]',f'set_load -pin_load {load} [get_ports {{{ports}}}]',
 'puts "BEGIN_SETUP"','report_worst_slack -max -digits 6','puts "BEGIN_HOLD"','report_worst_slack -min -digits 6','puts "BEGIN_ELECTRICAL"','report_check_types -max_slew -max_capacitance -violators -digits 6','puts "LOAD_CHECK_COMPLETED"']
 tcl=out/'run.tcl';tcl.write_text('if {[catch {\n'+'\n'.join(commands)+'\n} message options]} {\n puts stderr "LOAD_STA_FATAL: $message"\n exit 1\n}\nexit 0\n')
 r=subprocess.run(['openroad','-exit','-no_splash',str(tcl)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=45);(out/'sta.log').write_text(r.stdout)
 if r.returncode or 'LOAD_CHECK_COMPLETED' not in r.stdout or re.search(r'(^|\n)Error:',r.stdout):raise RuntimeError(name)
 e=r.stdout.split('BEGIN_ELECTRICAL',1)[1].split('LOAD_CHECK_COMPLETED',1)[0]
 result={'case':name,'load_pf':load,'electrical_limits_passed':'VIOLATED' not in e,'violation_rows':e.count('(VIOLATED)'), 'setup_slack_ns':float(re.search(r'BEGIN_SETUP.*?worst slack\s+(-?[\d.]+)',r.stdout,re.S)[1]),'hold_slack_ns':float(re.search(r'BEGIN_HOLD.*?worst slack\s+(-?[\d.]+)',r.stdout,re.S)[1]),'note':'Timing values at a load beyond characterized max-capacitance limits are extrapolated and are not timing signoff.'}
 return result
jobs=[(load,*corner) for load in [1,5] for corner in corners]
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:results=list(ex.map(run,jobs))
(base/'summary.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))
