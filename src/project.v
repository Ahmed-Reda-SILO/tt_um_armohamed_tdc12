`default_nettype none
// SPDX-License-Identifier: Apache-2.0
module tt_um_armohamed_tdc12 (
    input wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input wire ena,
    input wire clk,
    input wire rst_n
);
    wire [11:0] width_code;
    wire data_valid, busy, overflow;
    // Deselection clears state at a clock edge and releases the uio drivers.
    wire measurement_reset_n = rst_n & ena;
    pulse_width_tdc measurement (
        .clk(clk), .rst_n(measurement_reset_n), .pulse_in(ui_in[0]),
        .width_code(width_code), .data_valid(data_valid),
        .busy(busy), .overflow(overflow)
    );
    assign uo_out = width_code[7:0];
    assign uio_out = {1'b0, overflow, busy, data_valid, width_code[11:8]};
    assign uio_oe = {1'b0, {7{ena}}};
    wire _unused = &{ui_in[7:1], uio_in, 1'b0};
endmodule
`default_nettype wire
