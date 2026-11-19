#!/usr/bin/env python3
"""Compare simulator-read cell path delays against every input SDF arc."""
import argparse,collections,concurrent.futures,csv,json,subprocess
from pathlib import Path
from prepare_timed_model import sexpr,walk,value
p=argparse.ArgumentParser();p.add_argument('--vpi-include',type=Path,default=Path('/usr/include/iverilog'));a=p.parse_args()
root=Path(__file__).resolve().parents[1]
subprocess.run(['gcc','-fPIC','-shared','-O2','-I',str(a.vpi_include),'-o',str(root/'build/read_timing_paths.vpi'),str(root/'test/read_timing_paths.c')],check=True)
s=json.loads((root/'reports/sine_summary.json').read_text())
variants=[m['variant'] for m in s['models'] if m['variant']['stage'] not in ['rtl','zero_control']]
def run(v):
    folder=root/'build'/v['name'];out=root/'reports/annotation'/v['name'];out.mkdir(parents=True,exist_ok=True)
    cmd=['vvp','-M',str(root/'build'),'-m','read_timing_paths',str(folder/'simulation.vvp'),'+sdf='+str(folder/'cells.sdf'),
        '+stimulus='+str(root/'stimulus/zero_cross_10000Hz.txt'),'+finish_ns=212250']
    rp=subprocess.run(cmd,cwd=out,capture_output=True,text=True,timeout=30);(out/'simulation.log').write_text(rp.stdout+rp.stderr)
    if rp.returncode or 'PASS:' not in rp.stdout:raise RuntimeError(v['name'])
    expected=[]
    for c in walk(sexpr((folder/'cells.sdf').read_text()),'CELL'):
        inst=next(walk(c,'INSTANCE'))[1]
        for arc in walk(c,'IOPATH'):
            delays=[x for x in arc if isinstance(x,list)]
            expected.append((inst,arc[1],arc[2],round(value(delays[0]),6),round(value(delays[1]),6)))
    observed=[]
    with (out/'annotation_paths.csv').open() as f:
        for r in csv.DictReader(f):observed.append((r['instance'].removeprefix('sine_wave_tb.dut.'),r['source_pin'],r['destination_pin'],round(float(r['rise_ns']),6),round(float(r['fall_ns']),6)))
    e,o=set(expected),set(observed)
    result={'variant':v['name'],'passed':e==o,'cell_iopaths_expected':len(expected),'cell_iopaths_read_back':len(observed),
        'unique_pin_paths_read_back':len(o),'missing_or_wrong_paths':sorted(e-o),'unexpected_paths':sorted(o-e)}
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    if e!=o:raise RuntimeError(json.dumps(result))
    return result
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:result=list(ex.map(run,variants))
(root/'reports/annotation_summary.json').write_text(json.dumps(result,indent=2)+'\n')
print('PASS:',len(result),'timing models;',sum(r['cell_iopaths_expected'] for r in result),'actual simulator I/O-path delays match their SDF values')
