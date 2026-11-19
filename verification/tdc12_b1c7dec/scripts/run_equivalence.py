#!/usr/bin/env python3
"""Prove RTL/routed logical equivalence after reset synchronization."""
import argparse,json,pathlib,subprocess,re
p=argparse.ArgumentParser();p.add_argument('--pdk-root',required=True);a=p.parse_args()
root=pathlib.Path(__file__).resolve().parents[1];pdk=pathlib.Path(a.pdk_root).resolve()/'sky130A'
out=root/'reports/equivalence';out.mkdir(parents=True,exist_ok=True)
top='tt_um_armohamed_tdc12'
netlist=(root/'deliverables/nl'/f'{top}.nl.v').read_text()
removed=[]
def omit_power_only(match):
    if match[3].strip():raise RuntimeError('Physical-only cell unexpectedly has logical connections')
    removed.append({'cell':match[1],'instance':match[2]})
    return ''
netlist=re.sub(r'\b(sky130_fd_sc_hd__(?:tapvpwrvgnd|decap|fill)_\d+)\s+(\S+)\s*\((.*?)\);',omit_power_only,netlist,flags=re.S)
# OpenROAD writes the working-count bits as escaped scalar names. Recreate a
# read-only bus alias so equiv_make can match the RTL register's public name.
count_bits=[f'\\measurement.working_count[{i}] ' for i in range(11,-1,-1)]
for bit in count_bits:
 if bit.strip() not in netlist:raise RuntimeError('Expected public counter bit missing: '+bit)
alias='\nwire [11:0] \\measurement.working_count ;\nassign \\measurement.working_count = {'+', '.join(count_bits)+'};\n'
netlist=netlist.replace('endmodule',alias+'endmodule')
logic_netlist=out/'routed_logic_only.v';logic_netlist.write_text(netlist)
(out/'omitted_power_only_cells.json').write_text(json.dumps(removed,indent=2)+'\n')
commands=[
 f'read_verilog {root}/src/project.v {root}/src/pulse_width_tdc.v',
 f'prep -top {top} -flatten',f'rename {top} gold','design -stash gold_design',
 f'read_liberty -ignore_miss_func -ignore_miss_dir {pdk}/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib',
 f'read_verilog {logic_netlist}',
 f'prep -top {top} -flatten',f'rename {top} gate','design -stash gate_design',
 'design -copy-from gold_design -as gold gold','design -copy-from gate_design -as gate gate',
 'equiv_make gold gate equiv','hierarchy -top equiv','equiv_simple',
 'equiv_induct -seq 8','equiv_status -assert']
script=out/'prove.ys';script.write_text('\n'.join(commands)+'\n')
with (out/'yosys.log').open('w') as log:r=subprocess.run(['yosys','-Q','-T','-s',str(script)],stdout=log,stderr=subprocess.STDOUT,timeout=180)
log=(out/'yosys.log').read_text()
success=r.returncode==0 and 'Equivalence successfully proven!' in log
(out/'summary.json').write_text(json.dumps({'passed':success,'method':'Yosys logical equivalence with temporal induction, combined with reset simulation','timing_or_metastability_proof':False},indent=2)+'\n')
print(log[-2500:])
if not success:raise SystemExit('RTL/ROUTED EQUIVALENCE NOT PROVEN')
