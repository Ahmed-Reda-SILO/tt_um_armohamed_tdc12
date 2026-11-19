#!/usr/bin/env python3
"""Reconstruct a compatible OpenDB from the unchanged official routed DEF/LEFs."""
import argparse, json, os, pathlib, subprocess
p=argparse.ArgumentParser();p.add_argument('--pdk-root',required=True);a=p.parse_args()
root=pathlib.Path(__file__).resolve().parents[1]
pdk=pathlib.Path(a.pdk_root).resolve()/'sky130A'
build=root/'build';build.mkdir(exist_ok=True)
out=root/'reports/native_db';out.mkdir(parents=True,exist_ok=True)
odb=build/'official_def_native.odb'
commands=[f'read_lef {{{pdk}/libs.ref/sky130_fd_sc_hd/techlef/sky130_fd_sc_hd__nom.tlef}}',
 f'read_lef {{{pdk}/libs.ref/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef}}',
 f'read_lef {{{pdk}/libs.ref/sky130_fd_sc_hd/lef/sky130_ef_sc_hd.lef}}',
 f'read_def {{{root}/deliverables/def/tt_um_armohamed_tdc12.def}}',
 f'write_db {{{odb}}}', 'puts "OFFICIAL_DEF_IMPORT_COMPLETED"']
tcl=out/'import.tcl'
tcl.write_text('if {[catch {\n'+'\n'.join(commands)+'\n} message options]} {\n puts stderr "IMPORT_FATAL: $message"\n puts stderr [dict get $options -errorinfo]\n exit 1\n}\nexit 0\n')
r=subprocess.run(['openroad','-exit','-no_splash',str(tcl)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=90)
(out/'import.log').write_text(r.stdout)
if r.returncode or 'OFFICIAL_DEF_IMPORT_COMPLETED' not in r.stdout:raise RuntimeError(r.stdout[-5000:])
state={'odb':str(odb),'sdc':str(root/'deliverables/sdc/tt_um_armohamed_tdc12.sdc'),
 'spef':{rc+'_*':str(root/'deliverables/spef'/rc/('tt_um_armohamed_tdc12.'+rc+'.spef')) for rc in ['min','nom','max']}}
(build/'native_state.json').write_text(json.dumps(state,indent=2)+'\n')
print('PASS: official DEF imported; routed geometry, placement and connectivity unchanged')
