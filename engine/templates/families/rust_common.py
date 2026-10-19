"""Shared bare-metal Rust code generation for single/dual families (req-029)."""

from __future__ import annotations

from engine.core.plan import CorePlan

__all__ = ["hex32", "main_rs", "pre_init", "tpl"]


def tpl(text: str, **kw: object) -> str:
    for key, value in kw.items():
        text = text.replace(f"@{key}@", str(value))
    return text


def hex32(value: int) -> str:
    return f"0x{value:08X}"


def pre_init(core: CorePlan) -> str:
    """CPU2 release writes, emitted as the pre-RAM-init `__pre_init` hook."""
    if not core.release_writes:
        return ""
    lines = ["#[no_mangle]", 'pub unsafe extern "C" fn __pre_init() {']
    for addr, value, mask in core.release_writes:
        if mask:
            lines += [
                f"    let v = core::ptr::read_volatile({hex32(addr)} as *const u32);",
                f"    core::ptr::write_volatile("
                f"{hex32(addr)} as *mut u32, (v & !{hex32(mask)}) | {hex32(value)});",
            ]
        else:
            lines.append(
                f"    core::ptr::write_volatile({hex32(addr)} as *mut u32, {hex32(value)});"
            )
    lines.append("}")
    return "\n".join(lines) + "\n"


def main_rs(core: CorePlan) -> str:
    """Primary LED blink or sibling watchable counter (raw registers)."""
    pre = pre_init(core)
    if core.example_led is not None:
        led = core.example_led
        delay = round(0.25 * led.clock_hz / 5)
        on_shift = led.pin if led.active == "high" else led.pin + 16
        off_shift = led.pin + 16 if led.active == "high" else led.pin
        return tpl(
            """#![no_std]
#![no_main]

use cortex_m_rt::entry;
use panic_halt as _;

@PRE_INIT@
#[inline(never)]
unsafe fn delay_half_period() {
    for _ in 0..@ITERS@ {
        cortex_m::asm::nop();
    }
}

#[entry]
fn main() -> ! {
    unsafe {
        let rcc = @RCC@ as *mut u32;
        let moder = @MODER@ as *mut u32;
        let bsrr = @BSRR@ as *mut u32;

        let v = core::ptr::read_volatile(rcc);
        core::ptr::write_volatile(rcc, v | (1 << @RCC_BIT@));

        let v = core::ptr::read_volatile(moder);
        core::ptr::write_volatile(
            moder,
            (v & !(3 << (@PIN@ * 2))) | (1 << (@PIN@ * 2)),
        );

        loop {
            core::ptr::write_volatile(bsrr, 1 << @ON_SHIFT@);
            delay_half_period();
            core::ptr::write_volatile(bsrr, 1 << @OFF_SHIFT@);
            delay_half_period();
        }
    }
}
""",
            PRE_INIT=pre,
            ITERS=delay,
            RCC=hex32(led.rcc_en_addr),
            MODER=hex32(led.gpio_base),
            BSRR=hex32(led.gpio_base + 0x18),
            RCC_BIT=led.rcc_en_bit,
            PIN=led.pin,
            ON_SHIFT=on_shift,
            OFF_SHIFT=off_shift,
        )
    return tpl(
        """#![no_std]
#![no_main]

use cortex_m_rt::entry;
use panic_halt as _;

@PRE_INIT@
#[no_mangle]
pub static mut COUNTER: u32 = 0;

#[entry]
fn main() -> ! {
    loop {
        unsafe {
            let p = core::ptr::addr_of_mut!(COUNTER);
            let v = core::ptr::read_volatile(p);
            core::ptr::write_volatile(p, v.wrapping_add(1));
        }
        for _ in 0..@ITERS@ {
            cortex_m::asm::nop();
        }
    }
}
""",
        PRE_INIT=pre,
        ITERS=200_000,
    )
