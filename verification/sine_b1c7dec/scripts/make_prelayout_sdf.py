#!/usr/bin/env python3
"""Export cell-only delay SDF for the actual official pre-placement netlist."""
import argparse,concurrent.futures,json,re,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--audit-root',type=Path,required=True);p.add_argument('--pdk-root',type=Path,required=True);a=p.parse_args()
root=Path(__file__).resolve().parents[1];audit=a.audit_root.resolve();pdk=a.pdk_root.resolve()/'sky130A'
tags=sorted({s['corner'].split('_',1)[1] for s in json.loads((audit/'reports/sta/audited_summary.json').read_text())})
def run(tag):
    out=root/'reports/prelayout_sta'/tag;out.mkdir(parents=True,exist_ok=True)
    lines=[f'read_liberty {{{pdk}/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__{tag}.lib}}',
        f'read_lef {{{pdk}/libs.ref/sky130_fd_sc_hd/techlef/sky130_fd_sc_hd__nom.tlef}}',
        f'read_lef {{{pdk}/libs.ref/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef}}',
        f'read_lef {{{pdk}/libs.ref/sky130_fd_sc_hd/lef/sky130_ef_sc_hd.lef}}',
        f'read_verilog {{{audit}/official_artifacts/GDS_logs/runs/wokwi/06-yosys-synthesis/tt_um_armohamed_tdc12.nl.v}}',
        'link_design tt_um_armohamed_tdc12',f'read_sdc {{{audit}/deliverables/sdc/tt_um_armohamed_tdc12.sdc}}',
        'set_propagated_clock [all_clocks]',f'write_sdf -include_typ -digits 6 {{{out}/tdc.sdf}}','puts "PRELAYOUT_SDF_COMPLETE"']
    tcl=out/'run.tcl';tcl.write_text('if {[catch {\n'+'\n'.join(lines)+'\n} message options]} {puts stderr $message;exit 1}\nexit 0\n')
    r=subprocess.run(['openroad','-exit','-no_splash',str(tcl)],capture_output=True,text=True,timeout=60)
    (out/'sta.log').write_text(r.stdout+r.stderr)
    if r.returncode or 'PRELAYOUT_SDF_COMPLETE' not in r.stdout:raise RuntimeError(tag+' '+r.stdout[-2000:])
    return {'corner':tag,'sdf':str(out/'tdc.sdf'),'scope':'Actual pre-placement synthesis netlist, Liberty cell delays, zero wire parasitics; not final hold signoff'}
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:result=list(pool.map(run,tags))
(root/'reports/prelayout_sta/summary.json').write_text(json.dumps(result,indent=2)+'\n')
print('Exported',len(result),'cell-only pre-layout SDF files')
