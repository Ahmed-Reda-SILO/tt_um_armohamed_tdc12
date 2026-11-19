#!/usr/bin/env python3
"""Plot measured audit results and build a report. Does not synthesize data."""
from pathlib import Path
import csv, hashlib, json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, white
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output'
OUT.mkdir(exist_ok=True)
BLUE, ORANGE, GREEN, INK = '#1767A6', '#D87323', '#227753', '#172C42'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8.5,
    'axes.spines.top':False,'axes.spines.right':False,'axes.labelcolor':INK,
    'text.color':INK,'axes.edgecolor':'#8392a2','grid.alpha':.18,
    'savefig.facecolor':'white','figure.facecolor':'white'})

def load(path): return json.loads((ROOT/path).read_text())
sta = load('reports/sta/audited_summary.json')
pad = load('reports/pad_load/summary.json')
spice = []
for p in sorted((ROOT/'reports/rc_spice').glob('*/summary.json')):
    d=json.loads(p.read_text()); d['_folder']=p.parent; spice.append(d)
pre=next(s for s in spice if s['stage']=='prelayout')
post=next(s for s in spice if s['stage']=='extracted' and s['corner']=='tt')
ideal=next(s for s in spice if s['stage']=='routed_ideal_wire')
slow=next(s for s in spice if s['corner']=='ss')
fast=next(s for s in spice if s['corner']=='ff')
for d in [pre,post,ideal,slow,fast]:
    assert d['passed'] and d['samples_checked']==21 and len(d['errors'])==0
assert all(x['electrical_limits_passed'] for x in sta) and len(sta)==30
assert all(x['passed'] for x in pad) and len(pad)==6
predata=np.loadtxt(pre['_folder']/'transient.tsv',skiprows=1)
postdata=np.loadtxt(post['_folder']/'transient.tsv',skiprows=1)

def save(fig,name):
    fig.savefig(OUT/name,dpi=240,bbox_inches='tight')
    plt.close(fig)
def finish(ax, xlabel=True):
    ax.grid(axis='x'); ax.set_xlim(0,21)
    if xlabel: ax.set_xlabel('Time (us)')
def code(d,vdd):
    return np.sum((d[:,1:13]>vdd/2).astype(np.int64)*(1<<np.arange(12)),axis=1)

# Comparison uses an actual synthesis netlist before placement, and actual GDS
# devices + extracted wire R/C after layout. The ideal-wire control is separate.
fig=plt.figure(figsize=(11.2,8.1),layout='constrained')
gs=fig.add_gridspec(5,2,height_ratios=[1,1,1,1,1.45])
ax=fig.add_subplot(gs[0,:]); t=postdata[:,0]*1e6
ax.plot(t,postdata[:,25]/1.8,color='#8193a5',lw=.9,label='CLK')
ax.plot(t,postdata[:,26]/1.8+1.5,color=INK,lw=1.2,label='PULSE +1.5')
ax.set_yticks([0,1,1.5,2.5],['0','1','0','1']);ax.set_ylabel('Input logic');finish(ax,False)
ax.legend(ncol=2,loc='upper right',fontsize=8)
for lo,hi,w in [(4.25,6.25,2),(8.25,11.25,3),(13.25,17.25,4)]:
    ax.annotate(f'{w} us',((lo+hi)/2,2.55),ha='center',fontsize=9)
for row,col,label in [(1,None,'Width code'),(2,13,'DATA_VALID'),(3,14,'BUSY')]:
    ax=fig.add_subplot(gs[row,:])
    for d,v,c,ls,lbl in [(predata,1.8,BLUE,'-','Pre-layout'),(postdata,1.8,ORANGE,'--','Post-layout RC')]:
        y=np.where(d[:,27]>v/2,code(d,v),np.nan) if col is None else d[:,col]/v
        ax.plot(d[:,0]*1e6,y,color=c,ls=ls,lw=1.25,label=lbl)
    ax.set_ylabel(label);finish(ax,row==3)
    ax.axvspan(0,1.8,color='#dbe3eb',alpha=.6,lw=0)
    if row==1:
        ax.set_ylim(-.25,4.65);ax.set_yticks(range(5));ax.legend(ncol=2,loc='upper left',fontsize=8)
        for x,value in [(9.2,2),(14.2,3),(20.2,4)]:ax.annotate(str(value),(x,value+.14),ha='center',fontsize=10)
ax=fig.add_subplot(gs[4,0])
for d,c,ls,lbl in [(predata,BLUE,'-','Pre-layout'),(postdata,ORANGE,'--','Post-layout RC')]:
    x=(d[:,0]-8.5e-6)*1e9;mask=(x>=-.4)&(x<=3)
    ax.plot(x[mask],d[mask,13],c=c,ls=ls,lw=1.5,label=lbl)
ax.axhline(.9,c='#888',ls=':',lw=.8);ax.set_xlim(-.4,3)
ax.set_xlabel('Time after 8.5 us clock edge (ns)');ax.set_ylabel('VALID (V)');ax.grid()
ax.set_title('Capture edge: real transistor voltages',loc='left',fontsize=9)
ax=fig.add_subplot(gs[4,1])
vals=[s['worst_observed_output_delay_ns'] for s in [pre,ideal,post,slow,fast]]
ax.bar(range(5),vals,color=[BLUE,'#829aad',ORANGE,'#9d4860',GREEN],width=.65)
ax.set_xticks(range(5),['Synthesis\nTT','Routed, ideal\nwires TT','Routed RC\nTT','Routed RC\nSS','Routed RC\nFF'])
ax.set_ylabel('Largest observed delay (ns)');ax.set_ylim(0,2.02);ax.grid(axis='y')
for k,v in enumerate(vals):ax.text(k,v+.045,f'{v:.3f}',ha='center',fontsize=8)
fig.suptitle('12-bit TDC: measured pre-layout and extracted post-layout simulation',fontsize=14,fontweight='bold')
fig.supxlabel('1 MHz clock | TT: 1.8 V, 25 C | tile load: 0.033442 pF per output | ideal supplies',fontsize=8)
save(fig,'TDC_Pre_Post_Extraction.png')

# Every tile-wrapper output voltage, including output-enable controls.
fig=plt.figure(figsize=(11.5,12.1),layout='constrained');gs=fig.add_gridspec(10,3,height_ratios=[1.1,1.1]+[1]*8)
for j,(idx,title) in enumerate([(25,'CLK'),(26,'Pulse input'),(27,'Reset / enable')]):
    ax=fig.add_subplot(gs[0,j]);ax.plot(t,postdata[:,idx],color=INK,lw=.9)
    if j==2:ax.plot(t,postdata[:,28],c=GREEN,ls='--',lw=.9,label='ENA');ax.legend(loc='lower right',fontsize=6)
    ax.set_title(title,fontsize=9);ax.set_ylim(-.1,2.0);finish(ax,False);ax.tick_params(labelbottom=False)
ax=fig.add_subplot(gs[1,:])
ax.plot(predata[:,0]*1e6,np.where(predata[:,27]>.9,code(predata,1.8),np.nan),color=BLUE,label='Pre-layout',lw=1.3)
ax.plot(t,np.where(postdata[:,27]>.9,code(postdata,1.8),np.nan),color=ORANGE,ls='--',label='Post-layout RC',lw=1.1)
ax.set_ylabel('Code');ax.set_ylim(-.25,4.65);ax.set_yticks(range(5));ax.legend(ncol=2,loc='upper left',fontsize=8);finish(ax,False);ax.tick_params(labelbottom=False)
names=[['uo_out[%d]'%i for i in range(8)],['uio_out[%d]'%i for i in range(8)],['uio_oe[%d]'%i for i in range(8)]]
for group in range(3):
    for bit in range(8):
        ax=fig.add_subplot(gs[2+bit,group]);col=1+group*8+bit
        ax.plot(predata[:,0]*1e6,predata[:,col],color=BLUE,lw=1.1)
        ax.plot(t,postdata[:,col],color=ORANGE,ls='--',lw=.95)
        lab=names[group][bit]+({12:' VALID',13:' BUSY',14:' OVF',15:' unused'}.get(group*8+bit,''))
        ax.set_ylabel(lab,fontsize=7.2);ax.set_ylim(-.12,2);ax.set_yticks([0,1.8]);ax.axvspan(0,1.8,color='#dbe3eb',alpha=.6,lw=0);finish(ax,bit==7)
        if bit!=7:ax.tick_params(labelbottom=False)
fig.suptitle('All 24 tile-wrapper outputs: pre-layout vs extracted post-layout',fontsize=13,fontweight='bold')
fig.supxlabel('Voltages in V. Shading: reset initialization. Unused inputs have no logical connection; randomized separately in digital tests.',fontsize=7.5)
save(fig,'TDC_All_Outputs_Extracted.png')

# Digital wrapper test: all 19 inputs and all 24 outputs, including unused inputs.
def read_wave(mode):
    rows=[]
    with (ROOT/f'reports/{mode}/waveform.csv').open() as f:
        for r in csv.DictReader(f):
            if float(r['time_ns'])>65000:break
            if all(v.lstrip('-').isdigit() for k,v in r.items() if k!='time_ns'):
                rows.append([float(r['time_ns'])]+[int(r[k]) for k in ['clk','rst_n','ena','ui_in','uio_in','uo_out','uio_out','uio_oe']])
    return np.array(rows)
rtl,gate=read_wave('rtl'),read_wave('gate')
fig,axs=plt.subplots(19,3,figsize=(12,13.2),sharex=True,layout='constrained')
cols=[ [('clk',1,None),('rst_n',2,None),('ena',3,None)]+[(f'ui_in[{i}]',4,i) for i in range(8)]+[(f'uio_in[{i}]',5,i) for i in range(8)],
       [(f'uo_out[{i}]',6,i) for i in range(8)]+[(f'uio_out[{i}]',7,i) for i in range(8)],
       [(f'uio_oe[{i}]',8,i) for i in range(8)]]
for c,signals in enumerate(cols):
    for row in range(19):
        ax=axs[row,c]
        if row>=len(signals):ax.axis('off');continue
        lab,idx,bit=signals[row]
        for data,color,ls in [(rtl,BLUE,'-'),(gate,ORANGE,'--')]:
            vals=data[:,idx].astype(np.int64); vals=vals if bit is None else ((vals>>bit)&1)
            ax.step(data[:,0]/1000,vals,where='post',c=color,ls=ls,lw=.8)
        ax.set_ylim(-.2,1.25);ax.set_yticks([0,1]);ax.set_ylabel(lab,fontsize=6.7);ax.set_xlim(0,65);ax.grid(axis='x')
        if row==len(signals)-1:ax.set_xlabel('Time (us)');ax.tick_params(labelbottom=True)
    axs[0,c].set_title(['All 19 inputs','16 output data/status bits','8 output-enable bits'][c],fontsize=10,pad=9)
fig.suptitle('Full wrapper digital regression: RTL (blue) and routed functional netlist (orange)',fontsize=12,fontweight='bold')
fig.supxlabel('Initial varied-width pulses. Gate models use unit delays; this plot is functional verification, not an RC or SDF simulation.',fontsize=8)
save(fig,'TDC_All_Ports_Digital.png')

fig,axs=plt.subplots(2,1,figsize=(10.8,6.1),layout='constrained')
tags=sorted({s['corner'].split('_',1)[1] for s in sta})
for rc,col,marker in [('min',BLUE,'o'),('nom',GREEN,'s'),('max',ORANGE,'^')]:
    rows=[next(s for s in sta if s['corner']==rc+'_'+tag) for tag in tags]
    for ax,key in zip(axs,['setup_slack_ns','hold_slack_ns']):
        ax.plot(range(len(tags)),[s[key] for s in rows],label=rc+' RC',c=col,marker=marker,ms=4,lw=1)
for ax in axs:
    ax.grid();ax.set_xticks(range(len(tags)));ax.set_xticklabels([x.replace('_','\n').replace('n40C','-40C') for x in tags],fontsize=7.5)
axs[0].set_ylabel('Setup slack (ns)');axs[0].set_ylim(597.7,599.6);axs[0].legend(ncol=3,loc='lower right')
axs[1].set_ylabel('Hold slack (ns)');axs[1].axhline(0,c='#9d4860',ls='--',lw=.8)
fig.suptitle('Extracted STA: all 30 available PVT / RC cases pass',fontsize=13,fontweight='bold')
fig.supxlabel('1 MHz | 200 ns input/output budgets | 0.25 ns uncertainty | 0.033442 pF tile load | no slew/cap/fanout violations',fontsize=8)
save(fig,'TDC_PVT_Timing.png')

fig=plt.figure(figsize=(10.8,6.4),layout='constrained');gs=fig.add_gridspec(2,2)
for i,(proc,col) in enumerate([('tt',BLUE),('ss',ORANGE),('ff',GREEN)]):
    rec=next(s for s in pad if s['process']==proc and s['mode']=='output')
    d=np.loadtxt(ROOT/'reports/pad_load'/rec['case']/'transient.tsv',skiprows=1)
    ax=fig.add_subplot(gs[0,:]) if i==0 else ax
    ax.plot(d[:,0]*1e9,d[:,2]/rec['vio_v'],c=col,label=f"{proc.upper()} {rec['vcore_v']:g}/{rec['vio_v']:g} V, {rec['temperature_c']} C",lw=1)
    ax.set_xlim(30,380);ax.set_ylabel('PAD / VIO');ax.set_xlabel('Time (ns)');ax.grid();ax.legend(fontsize=8,ncol=3,loc='lower center')
ax=fig.add_subplot(gs[1,0])
for proc,col in [('tt',BLUE),('ss',ORANGE),('ff',GREEN)]:
    rec=next(s for s in pad if s['process']==proc and s['mode']=='output');d=np.loadtxt(ROOT/'reports/pad_load'/rec['case']/'transient.tsv',skiprows=1)
    ax.plot(d[:,0]*1e9-50.5,d[:,2]/rec['vio_v'],c=col,label=proc.upper(),lw=1.2)
ax.axhline(.5,c='#888',ls=':',lw=.8);ax.set_xlim(-1,10);ax.set_xlabel('After input 50% edge (ns)');ax.set_ylabel('PAD / VIO');ax.grid();ax.set_title('First rising edge',loc='left',fontsize=9)
ax=fig.add_subplot(gs[1,1]);x=np.arange(3)
for mode,offset,col in [('output',-.17,BLUE),('bidir',.17,ORANGE)]:
    v=[next(s for s in pad if s['process']==p and s['mode']==mode)['max_observed_delay_ns'] for p in ['tt','ss','ff']]
    ax.bar(x+offset,v,width=.32,color=col,label=mode)
    for xx,vv in zip(x+offset,v):ax.text(xx,vv+.08,f'{vv:.3f}',ha='center',fontsize=7)
ax.set_xticks(x,['TT','SS','FF']);ax.set_ylabel('Largest observed pad delay (ns)');ax.set_ylim(0,5.7);ax.grid(axis='y');ax.legend(fontsize=8,ncol=2)
fig.suptitle('5 pF load: representative GPIO pad simulation, 6 / 6 cases pass',fontsize=13,fontweight='bold')
fig.supxlabel('Schematic sky130_fd_io__top_gpiov2 | strong CMOS DM=110 | ideal supplies | shared mux/package/PCB not included',fontsize=8)
save(fig,'TDC_5pF_Pad_PVT.png')

summary={
    'project':'tt_um_armohamed_tdc12','source_commit':'b1c7dec19f113eb7fe47a1986d12d9c465be0c28',
    'gds_sha256':hashlib.sha256((ROOT/'tt_submission/tt_um_armohamed_tdc12.gds').read_bytes()).hexdigest(),
    'open_pdks':'8afc8346a57fe1ab7934ba5a6056ea8b43078e71','nominal_core_vdd_v':1.8,
    'clock_hz':1000000,'lsb_seconds':1e-6,
    'rtl_and_gate':{'clock_checks_each':131508,'conversions_each':1064,'overflow_events_each':2,'conversion_records_identical':(ROOT/'reports/rtl/conversions.csv').read_bytes()==(ROOT/'reports/gate/conversions.csv').read_bytes(),'gate_delay_model':'functional unit delay, no SDF annotation'},
    'clock_stop_and_reselection':load('reports/clock_stop_summary.json'),
    'gds_drc_errors':load('reports/gds_device_extraction/summary.json')['native_magic_drc_errors'],
    'lvs':load('reports/device_lvs/metrics.json'),'formal_equivalence':load('reports/equivalence/summary.json'),
    'sta':{'cases':30,'all_pass':True,'minimum_setup_slack_ns':min(s['setup_slack_ns'] for s in sta),'minimum_hold_slack_ns':min(s['hold_slack_ns'] for s in sta),'cases_detail':sta},
    'spice':[{k:v for k,v in d.items() if k not in ['_folder','samples','errors']} for d in [pre,ideal,post,slow,fast]],
    'pad_5pf':[{k:v for k,v in d.items() if k not in ['samples','errors']} for d in pad],
    'direct_tile_loads':load('reports/before_after/load_sta/summary.json'),
    'limitations':['User tile and its digital wrapper verified; assembled shared mux/pad/package/board not verified.',
        'Transistor PEX includes GDS MOS geometry and cell capacitance plus OpenRCX intercell RC; intracell metal resistance not extracted.',
        'Ideal power sources; no assembled-chip dynamic IR/EM, package SI, aging or silicon yield qualification.',
        'No characterized synchronizer MTBF, statistical mismatch/Monte Carlo, or clock jitter sweep.',
        'Post-layout transistor pulse train is a 21 us directed test; broad randomized coverage is digital and timing is checked separately.',
        'No SDF-annotated gate simulation; public cell Verilog models lack specify timing arcs.',
        'Direct 5 pF on tile output pins fails characterized electrical limits; external load requires GPIO path verification.']}
assert summary['rtl_and_gate']['conversion_records_identical']
(OUT/'verification_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
with (OUT/'PVT_30_Cases.csv').open('w') as f:
    wr=csv.writer(f);wr.writerow(['corner','setup_slack_ns','hold_slack_ns','electrical_limit_violations'])
    wr.writerows([[s[k] for k in ['corner','setup_slack_ns','hold_slack_ns','electrical_limit_violations']] for s in sta])

# PDF: explicit pages and measured image bounds prevent table/plot clipping.
W,H=595.28,841.89; M=43; CW=W-2*M
cv=canvas.Canvas(str(OUT/'TDC12_Verification_Report.pdf'),pagesize=(W,H))
cv.setTitle('SKY130 TDC12 verification audit - b1c7dec');cv.setAuthor('Ahmed Reda Mohamed / verification audit')
normal=ParagraphStyle('normal',fontName='Helvetica',fontSize=9.1,leading=13.2,textColor=HexColor(INK),spaceAfter=7)
small=ParagraphStyle('small',parent=normal,fontSize=7.6,leading=10.4)
heading=ParagraphStyle('heading',parent=normal,fontSize=11.5,leading=15,textColor=HexColor(BLUE),spaceAfter=7)
page=0;y=0
def start(title,sub=''):
    global page,y
    if page:cv.showPage()
    page+=1;cv.setFillColor(HexColor(INK));cv.rect(0,H-99,W,99,fill=1,stroke=0)
    cv.setFillColor(white);cv.setFont('Helvetica',8);cv.drawString(M,H-29,'SKY130  |  TINY TAPEOUT  |  AUDIT OF b1c7dec  |  19 NOV 2026')
    cv.setFont('Helvetica-Bold',19);cv.drawString(M,H-58,title)
    cv.setFont('Helvetica',8.4);cv.drawString(M,H-80,sub)
    cv.setFillColor(HexColor('#64778b'));cv.setFont('Helvetica',7)
    cv.drawString(M,25,'User tile + digital wrapper. Full assembled-shuttle signoff remains separate.')
    cv.drawRightString(W-M,25,str(page));y=H-120
def para(s,style=normal):
    global y
    p=Paragraph(s,style);pw,ph=p.wrap(CW,1000)
    if y-ph<43:raise RuntimeError(f'Page {page} text overflow: {s[:40]}')
    p.drawOn(cv,M,y-ph);y-=ph+7
def table(rows,widths=None):
    global y
    content=[[Paragraph(str(c),small) for c in row] for row in rows]
    tab=Table(content,colWidths=widths or [CW/len(rows[0])]*len(rows[0]),hAlign='LEFT')
    tab.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),HexColor('#E8EFF5')),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('BOTTOMPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),6),
        ('LINEBELOW',(0,0),(-1,-1),.3,HexColor('#cbd5df'))]))
    tw,th=tab.wrap(CW,1000)
    if y-th<43:raise RuntimeError(f'Page {page} table overflow {th} at {y}')
    tab.drawOn(cv,M,y-th);y-=th+13
def picture(name,maxheight):
    global y
    im=ImageReader(str(OUT/name));iw,ih=im.getSize();scale=min(CW/iw,maxheight/ih)
    h,w=ih*scale,iw*scale
    if y-h<43:raise RuntimeError(f'Page {page} image overflow')
    cv.drawImage(im,M+(CW-w)/2,y-h,width=w,height=h,mask='auto');y-=h+10

start('Verification result','12-bit pulse-width TDC, 1 MHz reference clock, nominal core VDD = 1.8 V')
para('<b>The current user tile and its digital wrapper pass the checks below.</b> The results apply to the exact official GDS and source commit identified here. They support fabrication readiness of this macro within the tested conditions. They do not guarantee every fabricated die or the final assembled board.')
table([['Check','Measured result'],['RTL + routed functional test','PASS each: 131,508 clock checks; 1,064 conversions; 2 overflow events.'],['Stopped clock / tile reselection','PASS for RTL and routed functional models.'],['RTL / routed logical equivalence','PASS: 44 equivalence points, 0 unproven.'],['GDS DRC + independent device LVS','0 DRC errors; all 7 LVS mismatch/error metrics are 0.'],['Official Tiny Tapeout precheck','16 / 16 checks pass on the official artifact.'],['Extracted timing + electrical limits','30 / 30 PVT / RC cases pass, including setup, hold, max slew, cap and fanout.'],['Transistor transient comparison','5 / 5 cases pass; actual pre-layout, routed ideal-wire control, and 3 extracted corners.'],['Representative GPIO at 5 pF','6 / 6 pad-only PVT / mode cases pass.'],['5 pF directly on tile output','FAIL electrical limits at all 3 tested PVT / RC corners. Use the GPIO path.']], [165,CW-165])
para('Source commit: <b>b1c7dec19f113eb7fe47a1986d12d9c465be0c28</b><br/>GDS workflow run: <b>44509700612</b><br/>Open PDKs: <b>8afc8346a57fe1ab7934ba5a6056ea8b43078e71</b>',small)
para('GDS SHA256:<br/>'+summary['gds_sha256'][:32]+'<br/>'+summary['gds_sha256'][32:],small)

start('Operation and testbench coverage','Each complete positive pulse starts a fresh count; its falling edge captures the result.')
table([['Port','Meaning'],['clk / rst_n / ena','1 MHz reference / active-low synchronous reset / tile selection enable.'],['ui_in[0]','Asynchronous digital pulse input, followed by a two-stage synchronizer.'],['ui_in[7:1], uio_in[7:0]','Unused inputs; randomized during digital verification.'],['uo_out[7:0]','Result code bits [7:0].'],['uio_out[3:0]','Result code bits [11:8].'],['uio_out[4] / [5] / [6] / [7]','DATA_VALID / BUSY / OVERFLOW / constant 0.'],['uio_oe[7:0]','0x7f when selected, 0x00 when deselected; bit 7 always disabled.']], [160,CW-160])
para('<b>Resolution and range.</b> One count represents 1 us at 1 MHz. A 10 us pulse normally gives code 10; widths near a sampling edge can quantize to adjacent codes. The code saturates at 4095; overflow reports a sampled count above 4095. The previous result remains available during the next measurement.')
para('<b>Interface contract.</b> Hold reset low for at least two active clock edges after selection or reselection. A pulse already high through reset is ignored until a low level arms a complete new pulse. Provide a low interval greater than two clock periods with timing margin between pulses. DATA_VALID lasts one clock cycle. Capture the parallel code with a clocked receiver at the next rising edge while DATA_VALID is high; do not depend on slow software polling or asynchronous sampling of the VALID edge.')
para('<b>Digital coverage.</b> The testbench checks 3, 6, 10, 4 and 15 us pulses; all 12 one-hot result bits; 4094, 4095, 4096 and 5000 counts; 1000 randomized fractional widths and phases; 40 PWM samples of a 1 kHz sine at a 20 kHz carrier; reset and deselection abort; startup-high rejection; result retention; overflow; one-cycle VALID; unused-input independence; and all wrapper output bits.')
para('<b>Model distinction.</b> Routed digital tests use the PDK functional Verilog models with a 1 ns unit delay. They are not SDF-annotated simulation. Timing is checked with extracted STA, and the directed analog tests use actual transistors and extracted interconnect. Analog sine voltage requires a preceding voltage-to-time/PWM conversion stage.',small)

start('Before and after extraction','Actual synthesis devices before placement versus actual GDS devices with intercell R/C.')
picture('TDC_Pre_Post_Extraction.png',390)
table([['Model / condition','Cells','Largest observed delay'],['Pre-layout synthesis, TT 1.8 V / 25 C','108','0.436 ns'],['Routed devices, ideal intercell wires, TT','139','0.827 ns'],['Routed RC, TT 1.8 V / 25 C','139','0.898 ns'],['Routed max RC, SS 1.6 V / 100 C','139','1.713 ns'],['Routed min RC, FF 1.95 V / -40 C','139','0.548 ns']], [295,55,CW-350])
para('All five cases pass 21 clock samples and three conversions, with 2, 3 and 4 us pulse widths. All 24 output voltages pass 0.3/0.7 VDD logic thresholds when sampled 200 ns after the clock edge. Delay values are the largest 50% threshold delays observed in this directed test, not maximum chip delay or a jitter specification.',small)
para('The pre-layout and routed netlists differ after physical optimization. The routed ideal-wire control isolates the intercell-wire effect. Extracted simulations include GDS MOS geometry, intrinsic device effects, intracell metal capacitance and OpenRCX intercell R/C. Intracell metal resistance is not extracted. Supplies are ideal; power-only filler/decap/tap cells are retained in GDS/LVS and omitted from transient simulation.',small)

start('All extracted wrapper outputs','Blue: pre-layout. Orange: post-layout intercell RC. Identical pulse train and nominal supplies.')
picture('TDC_All_Outputs_Extracted.png',600)
para('Every data, status and output-enable voltage is plotted. These are tile terminals at a 0.033442 pF load per output; shared mux, physical pads and package are outside this extraction.',small)

start('All digital wrapper ports','The full digital test toggles unused inputs and checks independence of every wrapper output.')
picture('TDC_All_Ports_Digital.png',600)
para('The initial five varied-width pulses are shown. Full conversion records contain 1064 captures, and RTL/routed records are byte-identical. Small unit-delay transitions overlap at this microsecond scale. No SDF backannotation was performed; the public standard-cell models have no specify timing arcs.',small)

start('PVT and extracted timing','10 available characterized non-CCS library points multiplied by 3 RC corners = 30 cases.')
picture('TDC_PVT_Timing.png',318)
table([['PVT point','Lowest setup over RC (ns)','Lowest hold over RC (ns)']]+[[tag.replace('_',' ').replace('n40C','-40C'),f"{min(s['setup_slack_ns'] for s in sta if s['corner'].endswith(tag)):.6f}",f"{min(s['hold_slack_ns'] for s in sta if s['corner'].endswith(tag)):.6f}"] for tag in tags], [210,150,CW-360])
para('<b>Worst setup slack: 597.934692 ns</b> at max RC, SS / -40 C / 1.60 V. <b>Worst hold slack: 0.115358 ns</b> at min RC, FF / -40 C / 1.95 V. Slew, capacitance and fanout violations: zero in all 30 cases.',small)
para('The clock period is 1000 ns, I/O timing budgets are 200 ns, and clock uncertainty is 0.25 ns. Only the asynchronous pulse arrival is false-pathed; the first-to-second synchronizer path is timed. These 10 characterized points are not a full process x voltage x temperature Cartesian grid. SF/FS timing, statistical mismatch and synchronizer MTBF were not characterized.',small)

start('Physical verification of the GDS','Independent checks use the exact official Magic streamout and its recorded PDK revision.')
table([['Evidence','Result / scope'],['Official final GDS','845,622 bytes; 161 x 111.52 um; SHA256 on page 1.'],['Native GDS DRC rerun','0 error boxes using the exact PDK Magic full DRC style.'],['Official precheck','16 / 16: Magic DRC; KLayout FEOL/BEOL/offgrid/pin-overlap/zero-area; boundary, pins, power, layers, cells and syntax.'],['Device-level LVS rerun','All 7 mismatch/error metrics are zero. Actual GDS transistor extraction is compared with the powered logical wrapper and transistor cell references.'],['LVS hierarchy','29 cell comparisons. Top-level connectivity matches; 15 disconnected input pins are the intentionally unused ui_in[7:1] and uio_in[7:0].'],['Device extraction safeguard','The original connectivity SPICE export contains black-box cells. It was rejected for transient simulation, then replaced with a real GDS device extraction.'],['Physical checks from official run','No final routing DRC, antenna or illegal-overlap violations.'],['Power and synchronizer','Both VPWR and VGND are connected; 32 DFF, distinct first and second synchronizer stages; their path remains timed.'],['RTL / routed equivalence','44 equivalence points proven, zero unproven; temporal induction holds at step 2. Power-only physical cells are omitted only in the formal adapter.']], [165,CW-165])
para('The official OpenDB uses a newer schema than the available native timing tool. The audit reconstructs a compatible database from the unchanged routed DEF and exact PDK LEFs; it does not move cells or reroute wires. SPEF and SDC remain those from the official run.',small)
para('Official run: <link href="https://github.com/Ahmed-Reda-SILO/tt_um_armohamed_tdc12/actions/runs/44509700612" color="#1767A6">GitHub Actions run 44509700612</link>. The production RTL and main branch are unchanged by this audit.',small)

start('What happens with 5 pF?','The physical GPIO driver and the internal standard-cell tile pin are different load points.')
picture('TDC_5pF_Pad_PVT.png',305)
table([['Pad test condition','Output delay (ns)','Bidirectional delay (ns)']]+[[f"{proc.upper()} {next(s for s in pad if s['process']==proc)['vcore_v']:g} V core / {next(s for s in pad if s['process']==proc)['vio_v']:g} V I/O",f"{next(s for s in pad if s['process']==proc and s['mode']=='output')['max_observed_delay_ns']:.3f}",f"{next(s for s in pad if s['process']==proc and s['mode']=='bidir')['max_observed_delay_ns']:.3f}"] for proc in ['tt','ss','ff']], [260,125,CW-385])
para('<b>Pad-only result:</b> all six cases pass 10 transitions each with a 5 pF pad load and a 5 MHz square-wave stimulus. The model is sky130_fd_io__top_gpiov2, strong CMOS DM=110, with separate core and I/O rails. Both dedicated output and bidirectional configurations pass. TT uses 1.8/3.3 V and 25 C; SS uses 1.6/3.0 V and 100 C; FF uses 1.95/3.6 V and -40 C.')
para('<b>Direct tile-pin result:</b> applying 1 pF or 5 pF directly to the 15 active data/status tile outputs violates standard-cell max capacitance/slew limits at all three tested PVT/RC conditions (42 reported violation rows per case). Timing extrapolation at these loads is not signoff. A 5 pF board load must be driven through the shuttle GPIO path.')
para('The pad tests use schematic PDK models and ideal supplies. They do not include extracted shared-mux wiring, pad-ring routing, package, PCB or simultaneous switching. One TT dedicated-output deck uses transient initialization (UIC) to bypass a DC convergence issue; the same transistor model and stimulus are used. The final assembled path must still be checked.',small)

start('Fabrication readiness and next steps','Completed tile audit; remaining work concerns the assembled chip, board and silicon validation.')
para('<b>Supported conclusion.</b> No functional mismatch or macro DRC/LVS error was found in the tested revision. The tile has positive extracted setup/hold margins at all 30 available timing cases. The directed transistor tests reproduce the expected codes after extraction. Nominal core VDD is 1.8 V. The representative pad test uses 3.3 V I/O; the final board/shuttle specification controls actual pin voltage and sequencing.')
table([['Remaining item','Required evidence'],['Final Tiny Tapeout integration','Verify the imported macro revision and hash, final shared mux/pad-ring connectivity and DRC/LVS, integrated timing including clock/reset distribution and the 5 pF package/board load.'],['Supply / switching integrity','Use final power grid, package and board models to check IR drop, simultaneous switching, overshoot and rail sequencing; apply shuttle signoff criteria.'],['CDC and operating limits','Review synchronizer placement and characterize MTBF if a numerical reliability target is required; quantify source-clock jitter and receiver timing requirements.'],['Board / receiver test','Clocked capture of VALID plus all 12 data bits; verify pin mapping, I/O voltage, reset after selection and a low gap above 2 us with margin.'],['Silicon acceptance','Measure known widths and fractional phases; all code bits; saturation/overflow; reset/deselection/clock-stop; PWM sine train; supply/temperature sweeps; external 5 pF load. Compare measured codes and edges against this report.']], [155,CW-155])
para('<b>Evidence package.</b> The companion ZIP contains generated GDS/DEF/LEF/netlists/SPEF/SDC, actual SPICE decks and time-domain data, 30 timing logs/SDF files, DRC/LVS reports, digital conversion CSVs, plots and machine-readable summaries. The verification branch contains reproducible scripts and the stopped-clock testbench. The original broad testbench remains in the repository test directory.')
para('<b>Toolchain.</b> Official physical flow: LibreLane 3.0.14. Audit: Magic 8.3.704, Netgen, OpenROAD/OpenSTA, ngspice 44.2 KLU, Yosys 0.52, Icarus Verilog 12.0; exact Open PDKs revision on page 1. Public PDK and model accuracy, ideal supplies, finite simulation coverage and absent assembled-chip data limit any reliability claim.',small)
para('<b>No universal fabrication guarantee is possible.</b> This is a traceable verification result for one macro revision and the stated models, tests and operating conditions. It is not wafer-yield, aging, ESD/latch-up, package or silicon reliability certification.',small)
cv.save()
print(json.dumps({'output':str(OUT),'pdf_pages':page,'plots':5,'sta_cases':len(sta),'pad_cases':len(pad)},indent=2))
