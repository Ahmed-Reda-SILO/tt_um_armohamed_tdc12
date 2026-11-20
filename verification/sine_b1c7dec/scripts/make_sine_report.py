#!/usr/bin/env python3
"""Build measured sine plots, the port diagram and the combined verification report."""
from pathlib import Path
import argparse,csv,hashlib,json,re
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch,FancyArrowPatch
import fitz
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor,white
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph,Table,TableStyle
from reportlab.lib.styles import ParagraphStyle

p=argparse.ArgumentParser();p.add_argument('--audit-root',type=Path,required=True);a=p.parse_args()
ROOT=Path(__file__).resolve().parents[1];AUDIT=a.audit_root.resolve();OUT=ROOT/'output';OUT.mkdir(exist_ok=True)
S=json.loads((ROOT/'reports/sine_summary.json').read_text());ANN=json.loads((ROOT/'reports/annotation_summary.json').read_text())
CASES=json.loads((ROOT/'stimulus/cases.json').read_text());STA=json.loads((AUDIT/'reports/sta/audited_summary.json').read_text())
assert S['all_passed'] and len(ANN)==40 and all(r['passed'] for r in ANN)
BLUE,ORANGE,GREEN,RED,INK='#1767A6','#D87323','#237750','#AB3448','#172C42'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8.5,'text.color':INK,'axes.labelcolor':INK,
 'axes.spines.top':False,'axes.spines.right':False,'axes.edgecolor':'#8191a1','grid.alpha':.2,
 'savefig.facecolor':'white','figure.facecolor':'white'})
VARIANTS=['pre_tt_025C_1v80','post_nom_tt_025C_1v80']
def case(name):return next(c for c in CASES if c['name']==name)
def result(name,variant=VARIANTS[1]):return next(r for r in S['results'] if r['case']==name and r['variant']==variant)
def conversions(name,variant):
 with (ROOT/'reports/sine'/variant/name/'conversions.csv').open() as f:return list(csv.DictReader(f))
WAVES={}
def wave(name,variant):
 key=(name,variant)
 if key not in WAVES:
  rows=[]
  with (ROOT/'reports/sine'/variant/name/'waveform.csv').open() as f:
   for r in csv.DictReader(f):
    try:row=[float(r['time_ns'])]+[int(r[k]) for k in ['clk','rst_n','ena','ui_in','uio_in','uo_out','uio_out','uio_oe']]
    except ValueError:continue
    rows.append(row)
  WAVES[key]=np.array(rows)
 return WAVES[key]
def code(w):return w[:,6].astype(np.int64)+256*(w[:,7].astype(np.int64)&15)
def bit(w,b):return (w[:,7].astype(np.int64)>>b)&1
def save(fig,name,svg=False):
 fig.savefig(OUT/name,dpi=240,bbox_inches='tight')
 if svg:fig.savefig(OUT/Path(name).with_suffix('.svg'),bbox_inches='tight')
 plt.close(fig)
def hzlabel(f):return {100:'0.1 kHz',1000:'1 kHz',10000:'10 kHz'}[f]
def sine_case_plot(f):
 name=f'pwm_{f}Hz_20000Hzcarrier';c=case(name);duration=2e3/f
 fig,axs=plt.subplots(6,1,figsize=(11.3,10),layout='constrained',gridspec_kw={'height_ratios':[1.2,.7,1.2,1.2,.65,.8]})
 fine=np.linspace(0,duration,1801);ref=np.sin(2*np.pi*f*fine*1e-3)
 frames=np.array([d['start_ns']-8250 for d in c['pulses']])/1e6
 refs=np.array([d['sine_normalized'] for d in c['pulses']])
 axs[0].plot(fine,.9+.6*ref,c='#687e92',lw=1.1,label='Ideal external sine reference')
 axs[0].plot(frames,.9+.6*refs,'o',c=BLUE,ms=2.5,label='Encoder sample times')
 axs[0].set_ylabel('Sine reference (V)');axs[0].set_ylim(.15,1.65);axs[0].legend(ncol=2,loc='upper right',fontsize=8)
 post=wave(name,VARIANTS[1]);tx=(post[:,0]-8250)/1e6
 axs[1].step(tx,post[:,4].astype(np.int64)&1,where='post',c=INK,lw=.8);axs[1].set_ylabel('ui_in[0]\nPWM logic')
 for v,col,ls,label in zip(VARIANTS,[BLUE,ORANGE],['-','--'],['Pre-layout cells','Post-layout RC timing']):
  w=wave(name,v);x=(w[:,0]-8250)/1e6
  axs[2].plot(x,code(w),c=col,ls=ls,lw=1.2,label=label)
  rows=conversions(name,v);codes=np.array([int(r['code_decimal']) for r in rows]);times=np.array([float(r['time_ns']) for r in rows])
  axs[2].plot((times-8250-200)/1e6,codes,'o',ms=2.7,c=col)
  axs[3].plot(frames,(codes-25)/20,marker='o',ms=2.8,lw=.8,c=col,ls=ls,label=label)
  axs[4].plot(x,bit(w,4),c=col,ls=ls,lw=.85)
 axs[2].set_ylim(-1,50);axs[2].set_ylabel('Actual width code');axs[2].legend(ncol=2,loc='upper right',fontsize=8)
 axs[3].plot(fine,ref,c='#a7afb7',lw=.9,zorder=0,label='Source sine')
 axs[3].set_ylim(-1.3,1.3);axs[3].set_ylabel('Decoded samples\n(code - 25) / 20')
 axs[4].set_ylabel('DATA_VALID');axs[4].set_yticks([0,1]);axs[4].set_xlabel('Time from first PWM frame (ms)')
 for ax in axs[:5]:ax.set_xlim(0,duration);ax.grid()
 detail=(post[:,0]>=8250+24000)&(post[:,0]<=8250+29000)
 axs[5].step((post[detail,0]-8250)/1000,post[detail,1],where='post',c='#62788f',lw=1,label='CLK, 1 MHz')
 axs[5].step((post[detail,0]-8250)/1000,bit(post[detail],4)+1.5,where='post',c=ORANGE,lw=1,label='VALID +1.5')
 axs[5].set_yticks([0,1,1.5,2.5],['0','1','0','1']);axs[5].set_ylabel('Clock / valid detail')
 axs[5].set_xlabel('Detail: time from first PWM frame (us)');axs[5].grid();axs[5].legend(ncol=2,loc='upper right',fontsize=8)
 verdict='UNDERSAMPLED: only 2 samples/cycle; this phase produces code 25' if f==10000 else f"{c['frames']//2} samples/cycle; output codes 5-45; 1 us timing step"
 fig.suptitle(hzlabel(f)+' sine: pre-layout vs extracted post-layout timing',fontsize=14,fontweight='bold')
 fig.supxlabel('PWM carrier = 20 kHz; width = 25 + 20 sin(theta) us. '+verdict+'\nDecoded samples use frame times; the code plot shows actual capture times. External encoder is ideal and outside the GDS.',fontsize=8)
 save(fig,{1000:'TDC_Sine_1kHz_Pre_Post.png',10000:'TDC_Sine_10kHz_Pre_Post.png',100:'TDC_Sine_0p1kHz_Pre_Post.png'}[f])
for f in [1000,10000,100]:sine_case_plot(f)

fig,axs=plt.subplots(5,3,figsize=(12,8.2),layout='constrained')
for j,f in enumerate([1000,10000,100]):
 name=f'pwm_{f}Hz_20000Hzcarrier';c=case(name);dur=2e3/f;fine=np.linspace(0,dur,1001)
 ref=np.sin(2*np.pi*f*fine*1e-3);frames=np.array([d['start_ns']-8250 for d in c['pulses']])/1e6
 axs[0,j].plot(fine,ref,c='#657d91',lw=1);axs[0,j].set_title(hzlabel(f)+f"; {c['frames']//2} samples/cycle",fontsize=10)
 post=wave(name,VARIANTS[1]);axs[1,j].step((post[:,0]-8250)/1e6,post[:,4].astype(np.int64)&1,where='post',c=INK,lw=.7)
 for v,col,ls in zip(VARIANTS,[BLUE,ORANGE],['-','--']):
  w=wave(name,v);x=(w[:,0]-8250)/1e6;codes=np.array([int(r['code_decimal']) for r in conversions(name,v)])
  axs[2,j].plot(x,code(w),c=col,ls=ls,lw=1.1)
  axs[3,j].plot(frames,(codes-25)/20,marker='o',ms=2.4,c=col,ls=ls,lw=.7)
  axs[4,j].plot(x,bit(w,4),c=col,ls=ls,lw=.7)
 axs[2,j].set_ylim(-1,50);axs[3,j].plot(fine,ref,c='#adb6be',lw=.8,zorder=0);axs[3,j].set_ylim(-1.3,1.3)
 for i in range(5):axs[i,j].set_xlim(0,dur);axs[i,j].grid()
 axs[4,j].set_xlabel('Time (ms)')
 if f==10000:axs[2,j].text(.04,.77,'Aliased: code = 25',transform=axs[2,j].transAxes,color=RED,fontsize=9)
for ax,label in zip(axs[:,0],['Sine reference\n(normalized)','PWM input logic','TDC width code','Decoded samples\n(normalized)','DATA_VALID']):ax.set_ylabel(label)
fig.suptitle('Three sine tests at a 1 MHz TDC clock: pre-layout vs extracted timing',fontsize=13,fontweight='bold')
fig.supxlabel('PWM carrier 20 kHz; widths 5-45 us. Blue: pre-layout cells. Orange: post-layout RC timing. Encoder external; full 43-port traces in report.',fontsize=8)
save(fig,'TDC_Three_Sine_Tests_Overview.png')

# Zero-crossing test: one high half-cycle per sine cycle.
fig,axs=plt.subplots(5,3,figsize=(12.3,8),layout='constrained')
for j,f in enumerate([1000,10000,100]):
 name=f'zero_cross_{f}Hz';duration=2e3/f;fine=np.linspace(0,duration,1201)
 axs[0,j].plot(fine,.9+.6*np.sin(2*np.pi*f*fine*1e-3),c=INK,lw=1);axs[0,j].set_title(hzlabel(f),fontsize=12)
 post=wave(name,VARIANTS[1]);x=(post[:,0]-8250)/1e6
 axs[1,j].step(x,post[:,4].astype(np.int64)&1,where='post',c=INK,lw=1)
 for v,col,ls in zip(VARIANTS,[BLUE,ORANGE],['-','--']):
  w=wave(name,v);x=(w[:,0]-8250)/1e6
  axs[2,j].plot(x,code(w),c=col,ls=ls,lw=1.2)
  axs[3,j].plot(x,bit(w,4),c=col,ls=ls,lw=1)
  axs[4,j].plot(x,bit(w,6),c=col,ls=ls,lw=1)
 for i in range(5):axs[i,j].set_xlim(0,duration);axs[i,j].grid()
 axs[2,j].text(.04,.84,['Code 500','Code 50','4095 + overflow'][j],transform=axs[2,j].transAxes,fontsize=10,c=RED if f==100 else GREEN)
 axs[4,j].set_xlabel('Time (ms)');axs[4,j].set_ylim(-.1,1.2)
for i,label in enumerate(['Sine reference (V)','ui_in[0] logic','Width code','DATA_VALID','OVERFLOW']):axs[i,0].set_ylabel(label)
fig.suptitle('Zero-crossing input: correct high-time counts and expected saturation',fontsize=14,fontweight='bold')
fig.supxlabel('Ideal comparator at 0.9 V; high pulse = half sine period. Blue: pre-layout cells. Orange: extracted post-layout timing. CLK = 1 MHz.',fontsize=8)
save(fig,'TDC_Zero_Crossing_Three_Frequencies.png')

# Faster PWM option for the 10 kHz input. This is a test of the current TDC;
# the analog encoder remains external and no production logic is changed.
fig,axs=plt.subplots(4,2,figsize=(11.5,7.3),layout='constrained')
for j,rate in enumerate([20000,100000]):
 name=f'pwm_10000Hz_{rate}Hzcarrier';c=case(name);fine=np.linspace(0,.2,1001);ref=np.sin(2*np.pi*10000*fine*1e-3)
 axs[0,j].plot(fine,ref,c='#9ba7b1',lw=1)
 for v,col,ls in zip(VARIANTS,[BLUE,ORANGE],['-','--']):
  r=conversions(name,v);codes=np.array([int(d['code_decimal']) for d in r]);frames=np.array([d['start_ns']-8250 for d in c['pulses']])/1e6
  axs[0,j].plot(frames,(codes-c['center_us'])/c['amplitude_us'],marker='o',c=col,ls=ls,ms=4,lw=.9)
  w=wave(name,v);x=(w[:,0]-8250)/1e6
  axs[1,j].step(x,w[:,4].astype(np.int64)&1,where='post',c=col,ls=ls,lw=.8)
  axs[2,j].plot(x,code(w),c=col,ls=ls,lw=1)
  axs[3,j].plot(x,bit(w,4),c=col,ls=ls,lw=.8)
 for i in range(4):axs[i,j].set_xlim(0,.2);axs[i,j].grid()
 axs[0,j].set_ylim(-1.3,1.3);axs[0,j].set_title(f'{rate//1000} kHz PWM: '+('2 samples/cycle' if rate==20000 else '10 samples/cycle'),fontsize=11)
 axs[3,j].set_xlabel('Time (ms)')
for ax,label in zip(axs[:,0],['Normalized sine / decoded','ui_in[0] logic','Width code','DATA_VALID']):ax.set_ylabel(label)
fig.suptitle('10 kHz sine at a 1 MHz TDC clock: sampling-rate and resolution trade-off',fontsize=13,fontweight='bold')
fig.supxlabel('20 kHz PWM: widths 5-45 us, alias at Nyquist. 100 kHz PWM: widths 3-7 us, only 5 nominal timing levels. Encoder outside GDS.',fontsize=8)
save(fig,'TDC_10kHz_Faster_PWM.png')

# All 43 logical ports. Detailed windows resolve the 1 MHz clock and conversion.
PORT_IMAGES=[]
for f in [1000,10000,100]:
 name=f'zero_cross_{f}Hz';half_us=5e5/f;lo_us=half_us-5;hi_us=half_us+15
 fig,axs=plt.subplots(19,3,figsize=(12,12.8),sharex=True,layout='constrained')
 cols=[[('clk',1,None),('rst_n',2,None),('ena',3,None)]+[(f'ui_in[{i}]',4,i) for i in range(8)]+[(f'uio_in[{i}]',5,i) for i in range(8)],
       [(f'uo_out[{i}]',6,i) for i in range(8)]+[(f'uio_out[{i}]',7,i) for i in range(8)],[(f'uio_oe[{i}]',8,i) for i in range(8)]]
 for j,signals in enumerate(cols):
  for i in range(19):
   ax=axs[i,j]
   if i>=len(signals):ax.axis('off');continue
   label,col,b=signals[i]
   for v,color,ls in zip(VARIANTS,[BLUE,ORANGE],['-','--']):
    w=wave(name,v);mask=(w[:,0]>=8250+lo_us*1000)&(w[:,0]<=8250+hi_us*1000);q=w[mask,col].astype(np.int64)
    if b is not None:q=(q>>b)&1
    ax.step((w[mask,0]-8250)/1000,q,where='post',c=color,ls=ls,lw=.85)
   ax.set_ylabel(label,fontsize=6.8);ax.set_yticks([0,1]);ax.set_ylim(-.2,1.25);ax.set_xlim(lo_us,hi_us);ax.grid(axis='x')
   if i==len(signals)-1:ax.set_xlabel('Frame-relative time (us)');ax.tick_params(labelbottom=True)
  axs[0,j].set_title(['All 19 inputs','All 16 data/status outputs','All 8 output-enable outputs'][j],fontsize=9)
 fig.suptitle(hzlabel(f)+' sine / zero crossing: every wrapper port before and after layout',fontsize=12,fontweight='bold')
 fig.supxlabel('Detail of first half-cycle capture. Blue: pre-layout cells. Orange: extracted timing. Frame-relative time refers to the first zero crossing.',fontsize=8)
 image=f'TDC_All_Ports_{f}Hz.png';PORT_IMAGES.append(image);save(fig,image)

# One measured capture edge proves nonzero SDF timing; the zero-delay control
# uses the same routed topology with all modeled delays deliberately zeroed.
name='zero_cross_10000Hz';edge=60500
fig,axs=plt.subplots(1,2,figsize=(11,3.65),layout='constrained')
for v,col,ls,label in [('pre_tt_025C_1v80',BLUE,'-','Pre-layout cells'),('post_nom_tt_025C_1v80',ORANGE,'--','Post-layout RC'),('post_zero_control','#8a98a7',':','Routed zero-delay control')]:
 if v=='post_zero_control':
  # The control's full nominal waveform was intentionally not retained. Its
  # actual output transition times are retained in arrivals.csv.
  rows=list(csv.DictReader((ROOT/'reports/sine'/v/name/'arrivals.csv').open()))
  rs=[r for r in rows if edge-10<=float(r['time_ns'])<=edge+10]
  first=next(float(r['time_ns']) for r in rs if r['valid']=='1')
  axs[0].step([-.2,first-edge,first-edge,1.5],[0,0,1,1],where='post',c=col,ls=ls,lw=1.5,label=label)
 else:
  w=wave(name,v);mask=(w[:,0]>=edge-1)&(w[:,0]<=edge+2)
  axs[0].step(w[mask,0]-edge,bit(w[mask],4),where='post',c=col,ls=ls,lw=1.5,label=label)
axs[0].set_xlim(-.2,1.5);axs[0].set_ylim(-.1,1.2);axs[0].grid();axs[0].set_xlabel('After 60.5 us clock edge (ns)');axs[0].set_ylabel('DATA_VALID logic');axs[0].legend(fontsize=7)
rcs=['min','nom','max'];tags=sorted({s['corner'].split('_',1)[1] for s in STA})
matrix=np.array([[sum(r['passed'] for r in S['results'] if r['variant']=='post_'+rc+'_'+tag) for tag in tags] for rc in rcs])
axs[1].imshow(matrix,vmin=0,vmax=7,cmap='Greens',aspect='auto')
for i in range(3):
 for j in range(10):axs[1].text(j,i,str(matrix[i,j])+'/7',ha='center',va='center',fontsize=7,c='white')
axs[1].set_xticks(range(10),[t.replace('_','\n').replace('n40C','-40C') for t in tags],fontsize=6.2)
axs[1].set_yticks(range(3),rcs);axs[1].set_title('Seven scenarios pass at each of 30 post-layout corners',fontsize=9)
fig.suptitle('Measured timing annotation and post-layout PVT coverage',fontsize=12,fontweight='bold')
save(fig,'TDC_SDF_Delay_Audit.png')

# Accurate engineering block/port diagram; the external encoder is explicitly
# outside the GDS boundary. This is not a new fabricated analog circuit.
fig,ax=plt.subplots(figsize=(11.8,8.2));ax.set_xlim(0,12);ax.set_ylim(0,9);ax.axis('off')
def box(x,y,w,h,text,color='#edf3f8',edge=BLUE,fs=10):
 patch=FancyBboxPatch((x,y),w,h,boxstyle='round,pad=.04,rounding_size=.10',facecolor=color,edgecolor=edge,lw=1.1);ax.add_patch(patch)
 ax.text(x+w/2,y+h/2,text,ha='center',va='center',fontsize=fs,color=INK)
def arrow(x0,y0,x1,y1,color=BLUE):ax.add_patch(FancyArrowPatch((x0,y0),(x1,y1),arrowstyle='-|>',mutation_scale=12,lw=1.3,color=color))
box(3.45,2.2,8.1,5.8,'',color='#f5f8fb',edge=BLUE)
ax.text(7.5,7.65,'Complete generated user-macro GDS',ha='center',fontsize=13,fontweight='bold')
ax.text(7.5,7.25,'tt_um_armohamed_tdc12  |  Tiny Tapeout digital wrapper included',ha='center',fontsize=9)
box(.25,6.65,2.7,1.15,'External sine reference\n0.1 / 1 / 10 kHz\n0.9 + 0.6 sin(2 pi f t) V',fs=9)
box(.25,4.65,2.7,1.35,'External ideal encoder\nZero-crossing comparator\nor sampled PWM',fs=10)
arrow(1.6,6.65,1.6,6.0)
box(3.9,5.0,2.0,1.15,'Two-stage\nsynchronizer',fs=11)
box(6.4,5.0,2.0,1.15,'12-bit counter\nsaturate at 4095',fs=10)
box(8.9,5.0,2.05,1.15,'Capture register\nVALID / BUSY / OVF',fs=9)
arrow(2.95,5.35,3.9,5.55);ax.text(3.35,6.05,'ui_in[0]',ha='center',fontsize=9,fontweight='bold')
arrow(5.9,5.55,6.4,5.55);arrow(8.4,5.55,8.9,5.55)
box(.25,2.55,2.7,1.4,'clk: 1 MHz\nrst_n: active-low reset\nena: tile selection',fs=10)
box(3.9,3.0,2.0,1.35,'Control / wrapper\nreset_n = rst_n & ena\nuio_oe control',fs=8.8)
arrow(2.95,3.35,3.9,3.65,GREEN)
ax.plot([4.8,10],[4.55,4.55],c=GREEN,lw=1.2);arrow(4.8,4.35,4.8,4.55,GREEN)
for x in [4.9,7.4,9.95]:arrow(x,4.55,x,5.0,GREEN)
box(6.4,3.0,4.55,1.1,'Result and status port mapping\n12 code bits + 3 flags + output enables',fs=10)
arrow(9.95,5.0,9.95,4.1)
ax.text(7.5,6.65,'ui_in[7:1], uio_in[7:0]: unused inputs (randomized in tests)',ha='center',fontsize=8.5,color='#63758a')
ax.text(7.45,2.5,'Physical power ports: VPWR = 1.8 V, VGND = 0 V',ha='center',fontsize=9,color=GREEN)
box(3.45,.35,8.1,1.35,'uo_out[7:0] = code[7:0]        uio_out[3:0] = code[11:8]\nuio_out[4] = VALID    [5] = BUSY    [6] = OVERFLOW    [7] = 0\nuio_oe[7:0] = 0x7F selected; 0x00 deselected',fs=10)
arrow(8.6,3.0,8.6,1.7)
ax.text(.3,.7,'Final shared mux, pad ring,\npackage and PCB require\nseparate integration evidence.',ha='left',va='center',fontsize=8.7,c=RED)
fig.suptitle('Sine-to-digital test system and associated ports',fontsize=15,fontweight='bold')
fig.text(.5,.025,'The analog encoder is a testbench model outside the GDS. No analog comparator or voltage-to-time circuit was added to silicon.',ha='center',fontsize=9,color=INK)
save(fig,'TDC_Block_Diagram.png',True)

def arrivals(v):
 rows=list(csv.DictReader((ROOT/'reports/sine'/v/'zero_cross_10000Hz'/'arrivals.csv').open()))
 return min(float(r['time_ns'])-60500 for r in rows if r['valid']=='1' and 60500<=float(r['time_ns'])<60502)
extra={'all_scenarios_pass':True,'full_macro_gds_sha256':S['gds_sha256'],'sine_cases':S['results'],
 'timing_annotation':{'models':40,'unique_pin_paths_checked':sum(r['cell_iopaths_expected'] for r in ANN),
 'conditional_path_records_read':sum(r['cell_iopaths_read_back'] for r in ANN),'all_readback_values_match':True,
 'example_valid_delay_ns':{v:arrivals(v) for v in [*VARIANTS,'post_zero_control']}},
 'postlayout_timing_cases':210,'postlayout_conversions_checked':sum(r['conversions'] for r in S['results'] if r['stage']=='postlayout'),
 'all_variant_clock_checks':sum(r['clock_checks'] for r in S['results']),'all_variant_conversions':sum(r['conversions'] for r in S['results']),
 'all_variant_expected_overflow_captures':sum(r['overflow_captures'] for r in S['results'])}
(OUT/'Sine_Verification_Summary.json').write_text(json.dumps(extra,indent=2)+'\n')

# New front section, followed by selected, corrected physical-audit evidence.
W,H=595.28,841.89;M=42;CW=W-2*M
cv=canvas.Canvas(str(OUT/'sine_report_front.pdf'),pagesize=(W,H));cv.setTitle('TDC12 full-macro sine verification')
normal=ParagraphStyle('normal',fontName='Helvetica',fontSize=9,leading=12.6,textColor=HexColor(INK))
small=ParagraphStyle('small',parent=normal,fontSize=7.6,leading=10.3)
page=0;y=0
def start(title,sub=''):
 global page,y
 if page:cv.showPage()
 page+=1;cv.setFillColor(HexColor(INK));cv.rect(0,H-98,W,98,fill=1,stroke=0)
 cv.setFillColor(white);cv.setFont('Helvetica',8);cv.drawString(M,H-27,'SKY130 TDC12  |  SINE VERIFICATION EXTENSION  |  19 NOV 2026')
 cv.setFont('Helvetica-Bold',18);cv.drawString(M,H-57,title)
 cv.setFont('Helvetica',8);cv.drawString(M,H-80,sub)
 cv.setFillColor(HexColor('#64758a'));cv.setFont('Helvetica',7);cv.drawString(M,24,'Complete generated user macro + digital wrapper; final shared mux/pads/package are separate.')
 cv.drawRightString(W-M,24,str(page));y=H-116
def para(text,style=normal):
 global y
 obj=Paragraph(text,style);_,h=obj.wrap(CW,1000)
 if y-h<44:raise RuntimeError(f'Page {page} overflow: {text[:50]}')
 obj.drawOn(cv,M,y-h);y-=h+8
def table(rows,widths=None):
 global y
 t=Table([[Paragraph(str(x),small) for x in row] for row in rows],colWidths=widths or [CW/len(rows[0])]*len(rows[0]))
 t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),HexColor('#e8eff6')),('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),('LINEBELOW',(0,0),(-1,-1),.3,HexColor('#cbd5df'))]))
 _,h=t.wrap(CW,1000)
 if y-h<44:raise RuntimeError(f'Page {page} table overflow')
 t.drawOn(cv,M,y-h);y-=h+10
def picture(name,height):
 global y
 im=ImageReader(str(OUT/name));iw,ih=im.getSize();scale=min(CW/iw,height/ih);w,h=iw*scale,ih*scale
 if y-h<44:raise RuntimeError(f'Page {page} image overflow')
 cv.drawImage(im,M+(CW-w)/2,y-h,w,h,mask='auto');y-=h+8

start('Three sine-input tests completed','1 MHz reference clock; pre-placement synthesis cells and full-macro extracted post-layout timing.')
para('<b>294 expected-behavior simulations pass:</b> 7 scenarios across RTL, 10 pre-layout cell corners, 30 post-layout PVT/RC corners and a routed zero-delay control. They cover 1,876,728 clock checks, 19,740 conversions and 84 correctly flagged overflow captures. Correct counter behavior does not imply useful amplitude reconstruction in every scenario.')
table([['Sine frequency','20 kHz PWM amplitude encoding','Zero-crossing high-time encoding'],['1 kHz','40 captures / 2 cycles; 20 samples/cycle; codes 5-45.','500 us high pulse; code 500; overflow 0.'],['10 kHz','4 captures / 2 cycles; 2 samples/cycle. This phase yields code 25 throughout: amplitude is undersampled.','50 us high pulse; code 50; overflow 0.'],['0.1 kHz (100 Hz)','400 captures / 2 cycles; 200 samples/cycle; codes 5-45.','5000 us high pulse; code 4095 with overflow 1: width is out of range.'],['10 kHz, faster-PWM option','100 kHz carrier, 10 samples/cycle, widths/codes 3-7. Variation is recovered with coarse amplitude resolution.','Same 1 MHz clock; no production RTL change.']], [79,220,CW-299])
para('<b>Scope.</b> The complete generated user-macro GDS and its digital Tiny Tapeout port wrapper are covered. All active routed cells are retained in the timed model. An ideal external comparator or sampled PWM encoder produces the digital input. The final shared multiplexer, pad-ring routing, package, PCB and physical analog encoder are outside this GDS.')
para('<b>Model.</b> Full-duration sine tests use event-driven cell timing and extracted SDF interconnect delays, with documented arc-envelope and negative-delay handling. These are not full-duration BSIM transistor transients. Earlier actual GDS-device/intercell-RC transistor tests remain supporting evidence in the appendix.')
para('Audited source: <b>b1c7dec19f113eb7fe47a1986d12d9c465be0c28</b><br/>Open PDKs: <b>8afc8346a57fe1ab7934ba5a6056ea8b43078e71</b><br/>Core VDD: <b>1.8 V nominal</b>; reference period: <b>1 us</b>.',small)
para('GDS SHA256:<br/>'+S['gds_sha256'][:32]+'<br/>'+S['gds_sha256'][32:],small)

start('Block diagram and port mapping','A sine voltage first requires a voltage-to-time/PWM or threshold encoder outside this digital macro.')
picture('TDC_Block_Diagram.png',365)
table([['Ports','Function'],['clk, rst_n, ena','1 MHz input clock; active-low synchronous reset; tile selection.'],['ui_in[0]','Digital pulse input, synchronized by two flip-flops.'],['ui_in[7:1], uio_in[7:0]','Unused; varied during every simulation to check independence.'],['uo_out[7:0], uio_out[3:0]','Width code bits [7:0] and [11:8], respectively.'],['uio_out[4], [5], [6], [7]','DATA_VALID, BUSY, OVERFLOW, constant 0.'],['uio_oe[7:0]','0x7F when ena=1; 0x00 when ena=0.'],['VPWR, VGND','Physical power ports; nominal 1.8 V core and ground.']], [170,CW-170])
para('A code is a measured duration, not a direct sine-amplitude ADC value. For the PWM examples, off-chip arithmetic reconstructs the normalized sample as (code - width_center_us) / width_amplitude_us. No DAC output or analog sine output is implemented.',small)

for f,filename in [(1000,'TDC_Sine_1kHz_Pre_Post.png'),(10000,'TDC_Sine_10kHz_Pre_Post.png'),(100,'TDC_Sine_0p1kHz_Pre_Post.png')]:
 start(hzlabel(f)+' sine: pre / post layout','PWM carrier 20 kHz; input widths 25 + 20 sin(theta) us; two complete sine periods.')
 picture(filename,485)
 name=f'pwm_{f}Hz_20000Hzcarrier';r=result(name);c=case(name)
 table([['Nominal result','Measured value'],['Captures / samples per sine cycle',f"{r['conversions']} / {c['frames']//2}"],['Output code range / overflow',f"{r['code_min']} to {r['code_max']} / {r['overflow_captures']}"],['Maximum absolute width error',f"{r['maximum_abs_width_error_us']:.3f} us (against actual guarded pulse width)"]], [250,CW-250])
 if f==10000:para('<b>Application limit:</b> two samples per sine cycle do not resolve a general 10 kHz waveform. At the tested zero phase, all sampled sine values are zero and the TDC correctly reports width/code 25. This is sampling aliasing, not a layout failure. The faster-PWM example on the next comparison page trades amplitude resolution for sample rate.',small)
 elif f==100:para('<b>Interpretation:</b> 200 PWM samples per sine cycle improve temporal sampling compared with 1 kHz, while the timing step remains 1 us. A direct zero-crossing high half-cycle is different: its 5 ms width exceeds the 4095-count range and sets overflow.',small)
 else:para('Pre-layout and post-layout codes agree. The first output is held at reset code 0 until a pulse is captured; subsequent results remain available while the next width is measured. DATA_VALID lasts one clock period. Decoded samples are plotted at encoder frame times; actual code publication occurs after the pulse falling edge and synchronization latency.',small)

start('Frequency, range and sample-rate limits','Zero-crossing measurement and PWM amplitude measurement answer different questions.')
picture('TDC_Zero_Crossing_Three_Frequencies.png',285)
picture('TDC_10kHz_Faster_PWM.png',285)
para('For an ideal 50% duty zero-crossing pulse, high time is 1/(2 f). The approximate unsaturated lower frequency is 122.1 Hz at 1 MHz and 12 bits; allow sampling-phase margin. Measuring a 100 Hz half-cycle needs more counter range or a slower clock. With PWM amplitude encoding, the carrier and width scale set the limits instead.',small)

start('Timing annotation, PVT and physical checks','All reported timing is tied to the unchanged official GDS, routed netlist and extracted parasitics.')
picture('TDC_SDF_Delay_Audit.png',235)
table([['Verification evidence','Result'],['Post-layout functional timing suite','210 / 210 runs: seven scenarios at each of 30 PVT/RC corners; 14,100 conversions.'],['Pre-layout comparison','70 / 70 runs at 10 characterized cell corners; zero interconnect RC.'],['Annotation readback audit','40 models pass; 10,010 unique pin paths and 17,050 conditional path records read from the simulator match the prepared timing data.'],['Wire-delay coverage','All 314 routed SDF interconnect entries mapped to explicit per-sink rise/fall delays in every post-layout timing model.'],['Measured example VALID delay',f"{arrivals(VARIANTS[0]):.6f} ns pre-layout; {arrivals(VARIANTS[1]):.6f} ns post-layout; {arrivals('post_zero_control'):.6f} ns in the zero-delay control."],['Extracted static timing (same GDS)','30 / 30 setup/hold/electrical cases pass; minimum setup 597.934692 ns, hold 0.115358 ns.'],['GDS DRC / device LVS / precheck','0 DRC errors; all seven LVS mismatch metrics zero; 16 / 16 official prechecks pass. Existing exact-GDS evidence is retained, not rerun per sine stimulus.']], [178,CW-178])
para('<b>Timing-model limits.</b> The STA SDF contains duplicate unconditional arcs for eight non-unate pin pairs. The adapter applies a per-transition maximum envelope to the corresponding PDK conditional paths. Negative characterized cell delays in nine fast post-layout variants are clamped to zero for causal event simulation. Original values remain in STA. Setup/hold/width notifiers and metastability are not simulated; separate extracted STA supplies timing-constraint checks.',small)
para('<b>Correction to the earlier report:</b> the PDK includes timing-enabled specify models. The earlier broad regression selected FUNCTIONAL models and used unit delays. This extension uses the original PDK specify I/O paths on unchanged functional logic, with explicit wire-delay handling for Icarus 12.',small)

for f,filename in zip([1000,10000,100],PORT_IMAGES):
 start(hzlabel(f)+' sine: every wrapper port','Zero-crossing encoding; detail around the first high-half-cycle capture. Clock remains 1 MHz.')
 picture(filename,595)
 para('All 19 logical inputs and all 24 logical outputs are represented. Unused inputs vary independently. Reset is already released and ena is high in this detail. All full-duration traces, all captures and the independent raw-width reference checks are included in the evidence package. Larger PNGs retain the labels at full resolution.',small)

start('Operating conditions and limitations','Verification supports the tested macro and conditions; it cannot guarantee every fabricated die.')
para('<b>Use conditions.</b> Keep the reference clock at 1 MHz for a 1 us code step. Reset for at least two active rising edges after tile selection/reselection. Start with a low pulse input; an input already high through reset is ignored until a low level arms a complete new pulse. Provide a low gap greater than two periods with margin. Capture all code/status bits with a clocked receiver at the next rising edge while DATA_VALID is high; ordinary software polling can miss the one-cycle flag.')
para('The 5-45 us PWM span gives 41 nominal timing levels, about 5.36 bits across that amplitude span. The 3-7 us faster-PWM span gives five levels, about 2.32 bits. A 12-bit register does not imply 12-bit amplitude resolution.',small)
table([['Item','Actual coverage / remaining limitation'],['Analog front end','Ideal 0.9 +/- 0.6 V sine reference. Comparator threshold 0.9 V or sampled PWM encoder is external. Encoder noise, nonlinearity, hysteresis and silicon implementation were not simulated.'],['Sampling phase','Pulse starts at quarter-clock phase. Widths are rounded to ns and moved by at most 50 ns away from a clock aperture; actual changes are retained in stimulus CSVs. These runs do not characterize metastability or edge jitter.'],['Statistical / PVT coverage','Ten available characterized NLDM cell points x min/nom/max RC. This is not a full Cartesian PVT grid or Monte Carlo/mismatch/aging qualification. All 30 post-layout variants reproduce expected integer codes for the guarded stimuli.'],['Transistor extraction','Existing directed BSIM tests use GDS MOS geometry, cell capacitance and intercell RC. Intracell metal resistance is not extracted; ideal supplies are used. Full 0.2/2/20 ms sine trains use the documented event-driven timing model.'],['External 5 pF load','Earlier representative schematic GPIO tests pass six PVT/mode cases. Direct 5 pF on tile outputs violates cell electrical limits. Final mux/pad/package/PCB timing, parasitics and simultaneous switching still require integration signoff.'],['Physical integrity','DRC/LVS/precheck and power connectivity match the same official GDS hash. Final assembled-shuttle DRC/LVS, power integrity, rail sequencing and silicon acceptance remain separate work.']], [140,CW-140])
para('<b>Evidence package.</b> Full sine stimuli, all conversion CSVs, nominal port waveforms, 294 logs/summaries, all 40 timing models/SDF files, 40 annotation readbacks, the unchanged generated GDS, SPEF, original DRC/LVS/precheck and prior transistor results are included. Source testbenches and rerun scripts are maintained on the verification branch. Production RTL and GDS were not redesigned.')
para('The following appendix pages retain selected corrected evidence from the earlier exact-GDS audit: transistor pre/post comparison, all 24 analog output voltages, the 30-corner timing matrix, DRC/LVS evidence, and the 5 pF pad tests.',small)
cv.save()
combined=fitz.open(OUT/'sine_report_front.pdf')
old=fitz.open(AUDIT/'output/TDC12_Verification_Report.pdf')
for n in [2,3,5,6,7]:combined.insert_pdf(old,from_page=n,to_page=n)
for n,pageobj in enumerate(combined):
 pageobj.draw_rect(fitz.Rect(W-75,H-36,W-25,H-13),color=None,fill=(1,1,1))
 pageobj.insert_text((W-48,H-24),str(n+1),fontsize=7,color=(.39,.46,.54))
combined.set_metadata({'title':'TDC12 complete-macro sine and physical verification','author':'Ahmed Reda Mohamed','subject':'1 kHz, 10 kHz and 0.1 kHz sine scenarios at 1 MHz; GDS b1c7dec'})
combined.save(OUT/'TDC12_Verification_Report.pdf',garbage=4,deflate=True)
print(json.dumps({'report':str(OUT/'TDC12_Verification_Report.pdf'),'pages':len(combined),'new_plots':11,
 'simulation_cases':S['simulation_cases'],'annotations_pass':True},indent=2))
