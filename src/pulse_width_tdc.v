`default_nettype none
// SPDX-License-Identifier: Apache-2.0
// Unsigned pulse-width measurement. All state changes use the reference clock.
module pulse_width_tdc (
    input wire clk,
    input wire rst_n,
    input wire pulse_in,
    output reg [11:0] width_code,
    output reg data_valid,
    output reg busy,
    output reg overflow
);
    (* async_reg = "true", keep = "true" *) reg pulse_meta;
    (* async_reg = "true", keep = "true" *) reg pulse_sync;
    reg pulse_previous;
    reg [11:0] working_count;
    reg working_overflow;
    reg armed;
    always @(posedge clk) begin
        if (!rst_n) begin
            // Initialize high so an input already high after reset cannot look
            // like a new rising edge. Arm only after a synchronized low level.
            pulse_meta <= 1'b1;
            pulse_sync <= 1'b1;
            pulse_previous <= 1'b1;
            armed <= 1'b0;
            working_count <= 12'd0;
            working_overflow <= 1'b0;
            width_code <= 12'd0;
            data_valid <= 1'b0;
            busy <= 1'b0;
            overflow <= 1'b0;
        end else begin
            pulse_meta <= pulse_in;
            pulse_sync <= pulse_meta;
            pulse_previous <= pulse_sync;
            data_valid <= 1'b0;
            busy <= armed && pulse_sync;
            if (!armed) begin
                working_count <= 12'd0;
                working_overflow <= 1'b0;
                if (!pulse_sync) armed <= 1'b1;
            end else if (pulse_sync) begin
                if (!pulse_previous) begin
                    working_count <= 12'd1;
                    working_overflow <= 1'b0;
                end else if (working_count != 12'hfff) begin
                    working_count <= working_count + 12'd1;
                end else begin
                    working_overflow <= 1'b1;
                end
            end else begin
                if (pulse_previous) begin
                    width_code <= working_count;
                    overflow <= working_overflow;
                    data_valid <= 1'b1;
                end
                working_count <= 12'd0;
                working_overflow <= 1'b0;
            end
        end
    end
endmodule
`default_nettype wire
