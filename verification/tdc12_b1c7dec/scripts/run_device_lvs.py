#!/usr/bin/env python3
"""Compare GDS-extracted MOS geometry with the powered wrapper reference."""
import argparse,json,pathlib,subprocess,re
from openlane.steps.netgen import get_metrics
p=argparse.ArgumentParser();p.add_argument('--pdk-root',required=True);a=p.parse_args()
root=pathlib.Path(__file__).resolve().parents[1];pdk=pathlib.Path(a.pdk_root).resolve()/'sky130A'
out=root/'reports/device_lvs';out.mkdir(parents=True,exist_ok=True)
layout=root/'reports/gds_device_extraction/devices_lvs.spice'
if not layout.exists():raise SystemExit('Run extract_gds_devices.py first')
source=root/'deliverables/pnl/tt_um_armohamed_tdc12.pnl.v'
library=pdk/'libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice'
setup=pdk/'libs.tech/netgen/sky130A_setup.tcl'
report=out/'lvs.rpt'; tcl=out/'compare.tcl'
tcl.write_text('\n'.join([
 f'set circuit1 [readnet spice {{{layout}}}]',
 'set circuit2 [readnet verilog /dev/null]',
 f'readnet spice {{{library}}} $circuit2',
 f'readnet verilog {{{source}}} $circuit2',
 f'lvs "$circuit1 tt_um_armohamed_tdc12" "$circuit2 tt_um_armohamed_tdc12" {{{setup}}} {{{report}}} -json',
 'quit'])+'\n')
with (out/'netgen.log').open('w') as log:
 r=subprocess.run(['netgen','-batch','source',str(tcl)],stdout=log,stderr=subprocess.STDOUT,cwd=out,timeout=180)
data=json.loads((out/'lvs.json').read_text())
metrics=get_metrics(data)
(out/'metrics.json').write_text(json.dumps(metrics,indent=2)+'\n')
print(json.dumps(metrics,indent=2))
if r.returncode or any(v!=0 for k,v in metrics.items() if 'lvs_' in k):raise SystemExit('DEVICE LVS FAIL: inspect lvs.rpt')
print('PASS: actual GDS device LVS against the complete powered wrapper')
