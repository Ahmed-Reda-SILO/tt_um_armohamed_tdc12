`timescale 1ns/1ps
`default_nettype none
module wrapper_clock_stop_tb;
 reg root_clk=0, clock_enable=1, rst_n=0, ena=1;
 reg [7:0] ui_in=0,uio_in=8'ha5;
 wire clk=root_clk & clock_enable;
 wire [7:0] uo_out,uio_out,uio_oe;
 wire [11:0] code={uio_out[3:0],uo_out};
`ifdef POWER_PINS
 supply1 VPWR; supply0 VGND;
`endif
 tt_um_armohamed_tdc12 dut(
`ifdef POWER_PINS
 .VPWR(VPWR),.VGND(VGND),
`endif
 .clk(clk),.rst_n(rst_n),.ena(ena),.ui_in(ui_in),.uio_in(uio_in),
 .uo_out(uo_out),.uio_out(uio_out),.uio_oe(uio_oe));
 always #500 root_clk=~root_clk;
 task measure(input integer width);
  begin
   @(negedge root_clk);ui_in[0]=1;
   repeat(width) @(negedge root_clk);ui_in[0]=0;
   wait(uio_out[4]===1'b1);#100;
   if(code!==width[11:0] || uio_out[6]!==0)$fatal(1,"Wrong width after selection/reset");
   @(negedge root_clk);
  end
 endtask
 initial begin
  $dumpfile("clock_stop.vcd");$dumpvars(0,wrapper_clock_stop_tb);
  repeat(3) @(negedge root_clk);rst_n=1;
  repeat(6) @(negedge root_clk);measure(10);
  @(negedge root_clk);ena=0;clock_enable=0;
  repeat(5) @(negedge root_clk);
  #100;if(uio_oe!==0 || clk!==0)$fatal(1,"Deselected wrapper did not release uio with stopped clock");
  @(negedge root_clk);ui_in[0]=1;rst_n=0;ena=1;clock_enable=1;
  repeat(3) @(negedge root_clk);rst_n=1;
  repeat(6) @(negedge root_clk);
  #100;if(code!==0 || uio_out[6:4]!==0 || uio_oe!==8'h7f)$fatal(1,"High input through reselection reset produced a partial result");
  @(negedge root_clk);ui_in[0]=0;
  repeat(6) @(negedge root_clk);measure(6);
  #100;$display("PASS: stopped-clock deselection, immediate output release, reselection reset, startup guard, fresh 6 us conversion");$finish;
 end
 initial begin #100000;$fatal(1,"Clock-stop test timed out");end
endmodule
`default_nettype wire
