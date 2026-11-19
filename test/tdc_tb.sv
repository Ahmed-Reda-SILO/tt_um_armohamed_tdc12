`timescale 1ns/1ps
`default_nettype none
module tdc_tb;
    reg clk=0, rst_n=0, ena=0;
    reg [7:0] ui_in=0, uio_in=0;
    wire [7:0] uo_out,uio_out,uio_oe;
    wire [11:0] code={uio_out[3:0],uo_out};
    wire valid=uio_out[4], busy=uio_out[5], overflow=uio_out[6];
`ifdef POWER_PINS
    supply1 VPWR;
    supply0 VGND;
`endif
    tt_um_armohamed_tdc12 dut (
`ifdef POWER_PINS
        .VPWR(VPWR),.VGND(VGND),
`endif
        .clk(clk),.rst_n(rst_n),.ena(ena),.ui_in(ui_in),.uio_in(uio_in),
        .uo_out(uo_out),.uio_out(uio_out),.uio_oe(uio_oe)
    );
    always #500 clk=~clk;
    integer cycle=0,checks=0,conversions=0,overflows=0;
    integer raw_count=0,pending_count=0,publish_at=-1,held_count=0;
    integer expected_valid=0,expected_busy=0,held_overflow=0;
    integer width_ns,gap_ns,k,n,expected_code,expected_overflow;
    reg last_raw=0,history0=0,history1=0,reference_armed=0,counted_high=0;
    reg [31:0] rng=32'hc1302026;
    integer out=0;
`ifdef WAVE_WINDOW
    integer waveform=0;
    initial begin
        waveform=$fopen("waveform.csv","w");
        $fwrite(waveform,"time_ns,clk,rst_n,ena,ui_in,uio_in,uo_out,uio_out,uio_oe\n");
    end
    always @(clk or rst_n or ena or ui_in or uio_in or uo_out or uio_out or uio_oe) begin
        if(waveform && $realtime<=2100000)
            $fstrobe(waveform,"%0.3f,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",$realtime,
                clk,rst_n,ena,ui_in,uio_in,uo_out,uio_out,uio_oe);
    end
`endif
    always @(negedge clk) begin
        rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
        ui_in[7:1]=rng[7:1]; uio_in=rng[15:8];
    end
    // Black-box reference: count raw high samples and publish two cycles after
    // the first sampled low edge. No DUT internal register is referenced.
    always @(posedge clk) begin
        cycle=cycle+1;
        expected_valid=0;
        if(!rst_n || !ena) begin
            raw_count=0; pending_count=0; publish_at=-1;
            held_count=0; held_overflow=0; expected_busy=0;
            last_raw=0; history0=0; history1=0;reference_armed=0;
        end else begin
            counted_high=ui_in[0] && reference_armed;
            if(!ui_in[0]) reference_armed=1;
            expected_busy=history1;
            history1=history0; history0=counted_high;
            if(counted_high) raw_count=raw_count+1;
            else if(last_raw) begin
                pending_count=raw_count; raw_count=0; publish_at=cycle+2;
            end
            last_raw=counted_high;
            if(cycle==publish_at) begin
                held_count=(pending_count>4095)?4095:pending_count;
                held_overflow=(pending_count>4095);
                expected_valid=1;
            end
        end
        #100;
        checks=checks+1;
        if(code !== held_count[11:0] || valid !== expected_valid[0]
           || busy !== expected_busy[0] || overflow !== held_overflow[0])
            $fatal(1,"Mismatch cycle=%0d code=%0d/%0d valid=%0d/%0d busy=%0d/%0d overflow=%0d/%0d",
                cycle,code,held_count,valid,expected_valid,busy,expected_busy,overflow,held_overflow);
        if(uio_oe !== (ena?8'h7f:8'h00) || uio_out[7] !== 1'b0)
            $fatal(1,"Tiny Tapeout wrapper mismatch");
        if(valid) begin
            conversions=conversions+1;
            if(overflow) overflows=overflows+1;
            if(out) $fwrite(out,"%0d,%0d,%0d,%0d,%0d\n",conversions,cycle,pending_count,code,overflow);
        end
    end
    task pulse(input integer width,input integer gap);
        begin
            width_ns=width;gap_ns=gap;
            if((($time+width_ns)%1000)==500) width_ns=width_ns+1;
            if((($time+width_ns+gap_ns)%1000)==500) gap_ns=gap_ns+1;
            ui_in[0]=1; #(width_ns); ui_in[0]=0; #(gap_ns);
        end
    endtask
    initial begin
`ifdef TRACE
        $dumpfile("tdc.vcd");$dumpvars(0,tdc_tb);
`endif
        out=$fopen("conversions.csv","w");
        $fwrite(out,"conversion,clock_cycle,raw_high_samples,code_decimal,overflow\n");
        #2250 ena=1;rst_n=1;
        #2000;
        pulse(3000,5000);pulse(6000,5000);pulse(10000,5000);
        pulse(4000,5000);pulse(15000,5000);
        // A complete 1 kHz sine encoded at 20 kHz for two cycles.
        for(n=0;n<40;n=n+1) begin
            width_ns=$rtoi(25000.0+20000.0*$sin(6.283185307179586*n/20.0)+0.5);
            pulse(width_ns,50000-width_ns);
        end
        // Every result bit, maximum count, overflow boundary, and saturation.
        pulse(1000,6000);
        for(k=1;k<12;k=k+1) pulse((1<<k)*1000,6000);
        pulse(4094000,6000);pulse(4095000,6000);
        pulse(4096000,6000);pulse(5000000,6000);pulse(7000,6000);
        // Fractional widths and phases, including the specified short gaps.
        for(n=0;n<1000;n=n+1) begin
            pulse(2001+(rng%200000),2001+((rng>>8)%9000));
        end
        // Reset aborts a pulse; no stale result may appear afterwards.
        ui_in[0]=1;#4200;rst_n=0;#3000;
        rst_n=1;#6000;ui_in[0]=0;#6000;pulse(9000,6000);
        // Deselection also clears measurement state and releases uio drivers.
        ui_in[0]=1;#4200;ena=0;#3000;
        ena=1;#6000;ui_in[0]=0;#6000;pulse(11000,6000);
        if(conversions!=1064 || overflows!=2)
            $fatal(1,"Coverage count conversions=%0d overflows=%0d",conversions,overflows);
        $display("PASS: %0d clock checks; %0d conversions; %0d overflow events; all wrapper ports, reset, deselection, fractional phases, sine train.",checks,conversions,overflows);
        $fclose(out);out=0;
`ifdef WAVE_WINDOW
        $fclose(waveform);waveform=0;
`endif
        $finish;
    end
endmodule
`default_nettype wire
