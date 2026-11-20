`timescale 1ns/1fs
`default_nettype none
module sine_wave_tb;
 reg clk=0,rst_n=0,ena=0;
 reg [7:0] ui_in=0,uio_in=0;
 wire [7:0] uo_out,uio_out,uio_oe;
 wire [11:0] code={uio_out[3:0],uo_out};
 wire valid=uio_out[4],busy=uio_out[5],overflow=uio_out[6];
`ifdef POWER_PINS
 supply1 VPWR;supply0 VGND;
`endif
 tt_um_armohamed_tdc12 dut(
`ifdef POWER_PINS
 .VPWR(VPWR),.VGND(VGND),
`endif
 .clk(clk),.rst_n(rst_n),.ena(ena),.ui_in(ui_in),.uio_in(uio_in),
 .uo_out(uo_out),.uio_out(uio_out),.uio_oe(uio_oe));
 always #500 clk=~clk;
 reg [4095:0] stimulus_path,sdf_path;
 integer sf,cf,wf=0,af=0,ret,starts,width,known_code,known_ov;
 integer total_pulses=0,cycle=0,checks=0,conversions=0,overflows=0;
 integer raw_count=0,pending_count=0,publish_at=-1,held_count=0;
 integer expected_valid=0,expected_busy=0,held_overflow=0;
 reg last_raw=0,history0=0,history1=0,reference_armed=0,counted_high=0;
 reg [31:0] rng=32'hc1302026;
 real finish_ns,last_clock_edge=0,edge_elapsed=0;
 initial begin
`ifdef TIMED_MODEL
  if(!$value$plusargs("sdf=%s",sdf_path))$fatal(1,"Missing SDF path");
  $sdf_annotate(sdf_path,dut);
`endif
  if(!$value$plusargs("stimulus=%s",stimulus_path))$fatal(1,"Missing stimulus path");
  if(!$value$plusargs("finish_ns=%f",finish_ns))$fatal(1,"Missing duration");
  if($test$plusargs("waves"))begin
   wf=$fopen("waveform.csv","w");af=$fopen("arrivals.csv","w");
   $fwrite(wf,"time_ns,clk,rst_n,ena,ui_in,uio_in,uo_out,uio_out,uio_oe\n");
   $fwrite(af,"time_ns,after_clock_ns,code,valid,busy,overflow\n");
  end
  cf=$fopen("conversions.csv","w");
  $fwrite(cf,"conversion,clock_cycle,time_ns,raw_high_samples,code_decimal,overflow\n");
  sf=$fopen(stimulus_path,"r");if(!sf)$fatal(1,"Cannot read stimulus");
  #1250;ena=1;#1000;rst_n=1;
  while(!$feof(sf))begin
   ret=$fscanf(sf,"%d %d %d %d\n",starts,width,known_code,known_ov);
   if(ret!=4)$fatal(1,"Invalid stimulus row");
   #(starts-$realtime);ui_in[0]=1;#(width);ui_in[0]=0;total_pulses=total_pulses+1;
  end
  #(finish_ns-$realtime);
  if(conversions!=total_pulses)$fatal(1,"Missing/extra conversions: %0d / %0d",conversions,total_pulses);
  $display("PASS: %0d clock checks; %0d conversions; %0d overflow captures; all 24 wrapper outputs checked",checks,conversions,overflows);
  $fclose(cf);if(wf)$fclose(wf);if(af)$fclose(af);$fclose(sf);$finish;
 end
 always @(negedge clk)begin
  rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};ui_in[7:1]=rng[7:1];uio_in=rng[15:8];
 end
 always @(posedge clk)begin
  last_clock_edge=$realtime;cycle=cycle+1;expected_valid=0;
  if(!rst_n||!ena)begin
   raw_count=0;pending_count=0;publish_at=-1;held_count=0;held_overflow=0;
   expected_busy=0;last_raw=0;history0=0;history1=0;reference_armed=0;
  end else begin
   counted_high=ui_in[0]&&reference_armed;if(!ui_in[0])reference_armed=1;
   expected_busy=history1;history1=history0;history0=counted_high;
   if(counted_high)raw_count=raw_count+1;
   else if(last_raw)begin pending_count=raw_count;raw_count=0;publish_at=cycle+2;end
   last_raw=counted_high;
   if(cycle==publish_at)begin
    held_count=(pending_count>4095)?4095:pending_count;
    held_overflow=(pending_count>4095);expected_valid=1;
   end
  end
  #200;checks=checks+1;
  if(code!==held_count[11:0]||valid!==expected_valid[0]||busy!==expected_busy[0]||overflow!==held_overflow[0])
   $fatal(1,"Mismatch cycle=%0d code=%0d exp=%0d valid=%b/%b busy=%b/%b ov=%b/%b",cycle,code,held_count,valid,expected_valid[0],busy,expected_busy[0],overflow,held_overflow[0]);
  if(uio_out[7]!==0||uio_oe!==((ena)?8'h7f:8'h00))$fatal(1,"Wrapper output/enable mismatch");
  if(valid)begin
   conversions=conversions+1;if(overflow)overflows=overflows+1;
   $fwrite(cf,"%0d,%0d,%0.6f,%0d,%0d,%0d\n",conversions,cycle,$realtime,pending_count,code,overflow);
  end
 end
 always @(clk or rst_n or ena or ui_in or uio_in or uo_out or uio_out or uio_oe)
  if(wf)$fstrobe(wf,"%0.6f,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",$realtime,clk,rst_n,ena,ui_in,uio_in,uo_out,uio_out,uio_oe);
 always @(uo_out or uio_out)if(af&&rst_n&&ena&&$realtime>8000)begin
  edge_elapsed=$realtime-last_clock_edge;
  $fstrobe(af,"%0.6f,%0.6f,%0d,%0d,%0d,%0d",$realtime,edge_elapsed,code,valid,busy,overflow);
 end
endmodule
`default_nettype wire
