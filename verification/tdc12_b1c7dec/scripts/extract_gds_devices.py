#!/usr/bin/env python3
"""Run GDS DRC and extract actual cell geometry, avoiding abstract LEF cells."""
import argparse,json,pathlib,re,subprocess,os,shutil
p=argparse.ArgumentParser();p.add_argument('--pdk-root',required=True);a=p.parse_args()
root=pathlib.Path(__file__).resolve().parents[1];pdk=pathlib.Path(a.pdk_root).resolve()/'sky130A'
out=root/'reports/gds_device_extraction';out.mkdir(parents=True,exist_ok=True)
gds=root/'tt_submission/tt_um_armohamed_tdc12.gds'
commands=[
 'drc off',f'gds read {{{gds}}}','load tt_um_armohamed_tdc12','select top cell',
 'drc euclidean on','drc style drc(full)','drc on','drc catchup',
 'set drc_result [drc listall why]','set drc_count 0',
 'foreach {reason boxes} $drc_result {incr drc_count [llength $boxes]}',
 'puts "AUDIT_DRC_COUNT $drc_count"',
 'set f [open drc_details.txt w]','puts $f [drc listall why]','close $f','drc off',
 f'extract path {{{out}}}','extract all','ext2spice lvs','ext2spice subcircuit on',
 f'ext2spice -o {{{out}/devices_lvs.spice}}',
 'ext2spice cthresh 0','ext2spice rthresh 0',
 f'ext2spice -o {{{out}/devices_with_cell_caps.spice}}',
 'puts "GDS_DEVICE_EXTRACTION_COMPLETED"','quit -noprompt']
tcl=out/'extract.tcl';tcl.write_text('\n'.join(commands)+'\n')
with (out/'magic.log').open('w') as log:
 r=subprocess.run(['magic','-dnull','-noconsole','-rcfile',str(pdk/'libs.tech/magic/sky130A.magicrc'),str(tcl)],cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=600,env={**os.environ,'PDK_ROOT':str(pdk.parent),'MAGTYPE':'mag'})
text=(out/'magic.log').read_text(errors='replace')
if r.returncode or 'GDS_DEVICE_EXTRACTION_COMPLETED' not in text:raise RuntimeError(text[-6000:])
spice=(out/'devices_lvs.spice').read_text()
mos=len(re.findall(r'(?im)^X\S*\s+.*?sky130_fd_pr__(?:nfet|pfet)',spice))
if mos<100:raise RuntimeError('Device extraction unexpectedly contains fewer than 100 MOS instances')
m=re.search(r'AUDIT_DRC_COUNT\s+(\d+)',text)
result={'gds':str(gds),'native_magic_drc_errors':int(m[1]) if m else None,'extracted_mos_in_cell_definitions':mos,'log':str(out/'magic.log')}
(out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
if not m or int(m[1])!=0:raise SystemExit('GDS DRC FAIL')
destination=root/'deliverables/spice/tt_um_armohamed_tdc12.spice'
destination.parent.mkdir(parents=True,exist_ok=True)
shutil.copy2(out/'devices_with_cell_caps.spice',destination)
