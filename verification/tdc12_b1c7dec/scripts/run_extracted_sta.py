#!/usr/bin/env python3
"""Run public OpenSTA commands against routed ODB + extracted SPEF.
Requires OpenROAD on PATH and PDK_ROOT containing sky130A.
"""
import argparse,concurrent.futures,json,os,pathlib,re,subprocess
p=argparse.ArgumentParser()
p.add_argument('--root',default=str(pathlib.Path(__file__).resolve().parents[1]))
p.add_argument('--pdk-root',default=os.environ.get('PDK_ROOT'))
p.add_argument('--state',help='Optional OpenLane state; defaults to delivered views')
p.add_argument('--all-characterized',action='store_true',help='All available NLDM process/temperature points between 1.60 and 1.95 V')
a=p.parse_args()
root=pathlib.Path(a.root).resolve();pdk=pathlib.Path(a.pdk_root).resolve()/'sky130A'

if a.state:
 s=json.load(open(a.state))
else:
 f=root/'deliverables'
 s={'odb':str(next((f/'odb').glob('*.odb'))),'sdc':str(next((f/'sdc').glob('*.sdc'))),'spef':{rc+'_*':str(next((f/'spef'/rc).glob('*.spef'))) for rc in ['min','nom','max']}}
out=root/'reports/sta';out.mkdir(parents=True,exist_ok=True)
tags=['tt_025C_1v80','ss_100C_1v60','ff_n40C_1v95']
if a.all_characterized:
 tags=[]
 for f in sorted((pdk/'libs.ref/sky130_fd_sc_hd/lib').glob('*.lib')):
  m=re.fullmatch(r'sky130_fd_sc_hd__(tt|ss|ff)_([n]?\d+)C_(\d+)v(\d+)\.lib',f.name)
  if m and 1.60<=float(m[3]+'.'+m[4])<=1.95:tags.append(f.stem.split('__',1)[1])
cases=[(rc,tag) for rc in ['min','nom','max'] for tag in tags]
def run(case):
 rc,tag=case;name=f'{rc}_{tag}';folder=out/name;folder.mkdir(exist_ok=True)
 spef=s['spef'][rc+'_*'];lib=pdk/'libs.ref/sky130_fd_sc_hd/lib'/f'sky130_fd_sc_hd__{tag}.lib'
 sdf=folder/'tdc.sdf'
 cmds=[f'read_liberty {{{lib}}}',f'read_db {{{s["odb"]}}}',f'read_sdc {{{s["sdc"]}}}',f'read_spef {{{spef}}}', 'set_propagated_clock [all_clocks]',
       'puts "BEGIN_SETUP"','report_worst_slack -max -digits 6','report_checks -path_delay max -group_count 5 -digits 6',
       'puts "BEGIN_HOLD"','report_worst_slack -min -digits 6','report_checks -path_delay min -group_count 5 -digits 6',
       'puts "BEGIN_ELECTRICAL"','report_check_types -max_slew -max_capacitance -max_fanout -violators -digits 6',
       'puts "BEGIN_ANNOTATION"','report_parasitic_annotation -report_unannotated',
       'puts "BEGIN_CONSTRAINTS"','check_setup -verbose',f'write_sdf -include_typ -digits 6 {{{sdf}}}',
       'puts "STA_COMMANDS_COMPLETED"']
 tcl=folder/'run.tcl';tcl.write_text('if {[catch {\n'+ '\n'.join(cmds)+'\n} message options]} {\n puts stderr "STA_FATAL: $message"\n puts stderr [dict get $options -errorinfo]\n exit 1\n}\nexit 0\n')
 r=subprocess.run(['openroad','-exit','-no_splash',str(tcl)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=90)
 (folder/'sta.log').write_text(r.stdout)
 if r.returncode or 'STA_COMMANDS_COMPLETED' not in r.stdout or re.search(r'(^|\n)Error:',r.stdout):
  raise RuntimeError(f'{name}: inspect {folder}/sta.log')
 setup=re.search(r'BEGIN_SETUP.*?worst slack\s+(-?[\d.]+)',r.stdout,re.S)
 hold=re.search(r'BEGIN_HOLD.*?worst slack\s+(-?[\d.]+)',r.stdout,re.S)
 if not setup or not hold:raise RuntimeError('Missing timing metrics: '+name)
 electrical=r.stdout.split('BEGIN_ELECTRICAL',1)[1].split('BEGIN_ANNOTATION',1)[0]
 violations=electrical.count('(VIOLATED)')
 result={'corner':name,'setup_slack_ns':float(setup[1]),'hold_slack_ns':float(hold[1]),'sdf':str(sdf),
         'electrical_limit_violations':violations,'electrical_limits_passed':violations==0}
 return result
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:results=list(ex.map(run,cases))
(out/'summary.json').write_text(json.dumps(results,indent=2))
(out/'audited_summary.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))
if any(x['setup_slack_ns']<0 or x['hold_slack_ns']<0 for x in results):raise SystemExit('TIMING FAIL')
if any(not x['electrical_limits_passed'] for x in results):raise SystemExit('ELECTRICAL LIMIT FAIL')
print(f'PASS: setup and hold at all {len(cases)} extracted PVT/RC combinations')
