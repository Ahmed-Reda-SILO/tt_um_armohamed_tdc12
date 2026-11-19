"""Portable Tiny Tapeout CI test, shared by RTL and gate-level simulation."""
import random
import cocotb
from cocotb.triggers import Timer

@cocotb.test()
async def verify_tdc(dut):
    rng=random.Random(13026)
    cycle=0; raw=0; previous=0; history=[0,0]
    held=0; saturated=0; publish=-1; pending=0; captures=0; armed=False
    dut.clk.value=0;dut.rst_n.value=0;dut.ena.value=0
    dut.ui_in.value=0;dut.uio_in.value=0

    async def step(pulse=0,reset_n=1,selected=1):
        nonlocal cycle,raw,previous,history,held,saturated,publish,pending,captures,armed
        dut.clk.value=0;dut.rst_n.value=reset_n;dut.ena.value=selected
        dut.ui_in.value=(rng.randrange(128)<<1)|pulse
        dut.uio_in.value=rng.randrange(256)
        await Timer(400,unit="ns")
        cycle+=1; valid=0; busy=0
        if not reset_n or not selected:
            raw=0;previous=0;history=[0,0];held=0;saturated=0;publish=-1;armed=False
        else:
            counted_high=pulse and armed
            if not pulse:armed=True
            busy=history[1];history=[counted_high,history[0]]
            if counted_high:raw+=1
            elif previous:pending=raw;raw=0;publish=cycle+2
            previous=counted_high
            if cycle==publish:
                held=min(pending,4095);saturated=int(pending>4095);valid=1
        dut.clk.value=1
        await Timer(100,unit="ns")
        observed=(int(dut.uio_out.value)&15)*256+int(dut.uo_out.value)
        assert observed==held,(cycle,observed,held)
        assert (int(dut.uio_out.value)>>4)==valid+2*busy+4*saturated
        assert int(dut.uio_oe.value)==(127 if selected else 0)
        captures+=valid
        await Timer(500,unit="ns")
        dut.clk.value=0

    await step(reset_n=0,selected=0)
    await step(pulse=1,reset_n=0)
    for _ in range(6):await step(pulse=1)
    for _ in range(5):await step()
    assert captures==0
    for width in [1,2,3,6,10,4,15,4095,4096,7]+[rng.randrange(2,70) for _ in range(40)]:
        for _ in range(width):await step(pulse=1)
        for _ in range(5):await step(pulse=0)
    assert captures==50
    for _ in range(4):await step(pulse=1)
    await step(reset_n=0)
    for _ in range(5):await step()
    assert held==0 and captures==50
    await step(selected=0)
    for _ in range(3):await step()
    dut._log.info("PASS: %d clock checks; %d completed conversions; reset, overflow, result retention and all wrapper outputs",cycle,captures)
