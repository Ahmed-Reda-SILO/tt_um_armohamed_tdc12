#!/usr/bin/env python3
"""Independent routed power-grid check and two-stage synchronizer path audit."""
import argparse,json,pathlib,subprocess,re
p=argparse.ArgumentParser();p.add_argument('--pdk-root',required=True)
a=p.parse_args();root=pathlib.Path(__file__).resolve().parents[1]
top='tt_um_armohamed_tdc12'
def register(name):
 routed=(root/'deliverables/pnl'/f'{top}.pnl.v').read_text()
 found=[]
 for m in re.finditer(r'\b(sky130_\w+)\s+(\\\S+|\w+)\s*\((.*?)\);',routed,re.S):
  if not m[1].startswith('sky130_fd_sc_hd__df'):continue
  ports=dict(re.findall(r'\.(\w+)\s*\(\s*([^)]*?)\s*\)',m[3]))
  if ports.get('Q','').strip().lstrip('\\')=='measurement.'+name:found.append(m[2].lstrip('\\'))
 assert len(found)==1,(name,found)
 return found[0]
meta=register('pulse_meta');sync=register('pulse_sync')
assert meta!=sync
out=root/'reports/connectivity';out.mkdir(exist_ok=True)
f=root/'deliverables';lib=pathlib.Path(a.pdk_root).resolve()/'sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib'
native_state=root/'build/native_state.json'
odb=json.loads(native_state.read_text())['odb'] if native_state.exists() else str(f/'odb'/f'{top}.odb')
commands=[f'read_liberty {{{lib}}}',f'read_db {{{odb}}}',
 f'read_sdc {{{f}/sdc/{top}.sdc}}',f'read_spef {{{f}/spef/nom/{top}.nom.spef}}',
 'set_propagated_clock [all_clocks]','set block [ord::get_db_block]']
for net in ['VPWR','VGND']:
 report=out/(net+'_errors.rpt')
 if report.exists():report.unlink()
 commands += [f'set grid_net [$block findNet {net}]','set shapes 0',
  'foreach swire [$grid_net getSWires] {incr shapes [llength [$swire getWires]]}',
  'if {$shapes == 0} {error "Empty power grid"}',
  f'check_power_grid -net {net} -error_file {{{report}}}',
  f'if {{[file exists {{{report}}}] && [file size {{{report}}}] > 0}} {{error "Power connectivity report is not empty"}}',
  f'puts "POWER_PASS {net} shapes=$shapes"']
for label,inst in [('META',meta),('SYNC',sync)]:
 commands += [f'set instance [$block findInst {{{inst}}}]',
  f'puts "{label}_LOCATION [$instance getLocation]"',
  f'puts "{label}_CELL [[$instance getMaster] getName]"']
commands += [f'set paths [find_timing_paths -from [get_pins {{{meta}/Q}}] -to [get_pins {{{sync}/D}}] -path_delay max]',
 'if {[llength $paths] != 1} {error "Synchronizer path is missing or unconstrained"}',
 f'report_checks -from [get_pins {{{meta}/Q}}] -to [get_pins {{{sync}/D}}] -path_delay max -digits 6',
 'puts "CONNECTIVITY_AND_CDC_PATH_PASS"']
tcl='if {[catch {\n'+'\n'.join(commands)+'\n} message options]} {\n puts stderr $message\n puts stderr [dict get $options -errorinfo]\n exit 1\n}\nexit 0\n'
(out/'check.tcl').write_text(tcl)
r=subprocess.run(['openroad','-exit','-no_splash',str(out/'check.tcl')],capture_output=True,text=True)
(out/'check.log').write_text(r.stdout+r.stderr)
if r.returncode or 'CONNECTIVITY_AND_CDC_PATH_PASS' not in r.stdout:raise RuntimeError('Inspect reports/connectivity/check.log')
(out/'summary.json').write_text(json.dumps({'passed':True,'first_stage_instance':meta,
 'second_stage_instance':sync,'first_to_second_stage_path_timed':True,
 'power_grids':['VPWR','VGND'],'mtbf_characterization_performed':False},indent=2)+'\n')
print(r.stdout)
