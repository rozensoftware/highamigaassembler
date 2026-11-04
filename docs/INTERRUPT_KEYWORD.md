# The `interrupt` / `starti` / `endi` keywords

Software VBlank dispatch slots for periodic (50Hz PAL / 60Hz NTSC) background
work, modeled on the AMOS Professional AMAL/`EVERY` channel system

## Syntax

```has
interrupt NAME(INDEX) -> void {
    // statements - no parameters, always void, no explicit return value
}

starti(INDEX);   // enable dispatch slot INDEX
endi(INDEX);     // disable dispatch slot INDEX
```

- `INDEX` is a compile-time integer literal, **0-15**.
- Each index may be declared by at most one `interrupt` proc in the program.
- `starti(X)`/`endi(X)` may appear in any proc body; the compiler checks that
  `X` was declared by an `interrupt` proc, and errors otherwise.

## Example

See [examples/interrupt_vbl_demo.has](../examples/interrupt_vbl_demo.has).

```has
extern func TakeSystem() -> void;
extern func ReleaseSystem() -> void;

bss counters:
    frame_count.l: 1

code main:
    asm { jmp main }

    interrupt vbl_counter(0) -> void {
        frame_count = frame_count + 1;
    }

    proc main() -> void {
        call TakeSystem();
        starti(0);
        // ... game loop ...
        endi(0);
        call ReleaseSystem();
        return;
    }
```

## Hardware model (and corrections to common assumptions)

The 68000 does **not** have "16 user interrupts". It has:

- 7 CPU priority levels (autovector interrupts 1-7, IPL0-2 lines) - not 16.
- 16 **software** trap vectors via `TRAP #0`-`TRAP #15` (vectors 32-47) - a
  different, unrelated mechanism (synchronous software traps, not periodic
  hardware interrupts).
- The 68000/68020 instruction to return from a real hardware/software
  exception is **`RTE`** ("ReTurn from Exception").

On the Amiga, periodic 50Hz/60Hz timing comes from a **single** hardware
source: the **VERTB** (vertical blank) interrupt, one bit (bit 5) of the
Paula/Agnus `INTENA`/`INTREQ` registers, routed through one CPU autovector
level. There is no hardware concept of "starting" or "stopping" one of 16
independent vectors - `INTENA`/`INTREQ` only have 14 real maskable source
bits total, and VERTB is just one of them.

Matching how AmigaOS's own `AddIntServer`/`SetIntVector` handlers work (and
how AMOS's AMAL/`EVERY` system works internally), this feature multiplexes
**16 software dispatch slots** off that single VERTB source:

1. The compiler auto-generates one hidden master VBlank ISR
   (`_has_vblank_isr`). On **every** `starti()` call, `_has_int_ensure_installed`
   checks whether the CPU's level-3 autovector ($6C) already points at this
   ISR; if not (first use, or after an intervening `ReleaseSystem()`/OS
   vector restore), it saves the current vector into `_has_old_vec3` and
   installs `_has_vblank_isr`. This check is self-correcting across repeated
   `TakeSystem()`/`starti()`/`ReleaseSystem()` cycles within one run.
2. `starti(X)` sets bit `X` in a 16-bit active-slot mask (`_has_int_mask`)
   and unmasks VERTB **and the master INTEN bit (bit 14)** in `INTENA`.
   This is deliberate: `lib/takeover.s`'s `TakeSystem()` clears the master
   INTEN bit along with everything else, and nothing else in a program that
   doesn't happen to call some other library function that also re-enables
   it (e.g. `InitKeyboard()`) would ever turn interrupts back on globally -
   `starti()` must not depend on that coincidence, so it always re-asserts
   INTEN itself. `endi(X)` clears bit `X`, and re-masks VERTB (but leaves
   INTEN alone - other subsystems may still need it) only once **no** slots
   remain active.
3. On every real VERTB interrupt, `_has_vblank_isr` acknowledges the
   interrupt, then walks the 16-slot dispatch table (`_has_int_slots`,
   `dc.l` per index, `0` for unused indices) and `jsr`s into every **active**
   slot in turn, finally executing a single `rte`.
4. Each `interrupt NAME(INDEX) -> void { ... }` proc is therefore a
   **dispatch slot**, not its own top-level exception handler: it still does
   a full `movem.l d0-d7/a0-a6,-(sp)` / `movem.l (sp)+,d0-d7/a0-a6` save and
   restore (as requested - no parameters, always void, no assumptions about
   caller-saved registers), but it must end in **`rts`** (it's `jsr`'d as a
   subroutine of the master ISR) - only the one hidden master ISR ends in
   `rte`. This exactly mirrors how real AmigaOS interrupt handlers/servers
   work (they also return via `RTS`, never `RTE` - only Exec's own installed
   autovector entry does that).

This design is deliberately **CPU-target-neutral**: no scaled/indexed
addressing or 68020-only instructions are used anywhere in the dispatch
loop or `starti`/`endi` codegen (plain `movem.l`/`bset`/`bclr`/`dbra`), so
the generated code is byte-identical in structure on both `--cpu 68000` and
`--cpu 68020` (only differs in that other, unrelated statements in the
interrupt proc body may use CPU-specific codegen as usual).

## Clean exit to DOS (`ReleaseSystem`)

`lib/takeover.s`'s `ReleaseSystem()` (paired with `TakeSystem()`) already
unconditionally clears **all** `INTENA`/`INTREQ` bits (`#$7fff`) before
restoring the OS's saved interrupt state, and saves/restores the
level-3 autovector at `VBRBase+$6C` (where this feature installs its master
VBlank ISR) alongside level-2/level-4 (`VBRBase+$68` / `+$70`).
`VBRBase` is 0 on 68000 and the relocated VBR on 68010+. This means calling
`ReleaseSystem()` before returning to DOS always disables VERTB and restores
the original vector, regardless of whether the program called `endi()` on
every slot it `starti()`'d - a program that forgets to `endi()` a slot still
exits cleanly as long as it calls `ReleaseSystem()`.

**Mandatory ordering**: always call `TakeSystem()` before the *first*
`starti()` in the program (also so `VBRBase` is initialized). If `starti()`
runs first, it installs `_has_vblank_isr` into `VBRBase+$6C` and stashes the
true original vector in its own `_has_old_vec3` - a variable
`TakeSystem()`/`ReleaseSystem()` don't know about. A subsequent
`TakeSystem()` call would then capture `_has_vblank_isr` itself (not the
real OS vector) into its `old_int3`, and `ReleaseSystem()` would "restore"
the vector right back to the (by-then-freed) interrupt handler instead of
the OS default - a dangling vector after the program exits.

In practice, always structure the program's entry exactly like this, with
`TakeSystem()` as the first instruction and `ReleaseSystem()` as the last:

```has
code main:
    public main;
    asm {
        jsr TakeSystem
        jsr main
        jmp ReleaseSystem
    }
    ...
```

## Interaction with `lib/keyboard.s` (and other level-2/level-6 handlers)

`starti(X)`/`endi(X)` never touch `lib/keyboard.s`'s level-2 autovector
(`$68`) or its `PORTS` `INTENA` bit (bit 3) - only `$6C`/VERTB (bit 5) are
touched, so there is no vector or bit-level collision with `InitKeyboard()`,
and none with `lib/ptplayer.s`'s level-6 CIA-B vector (`$78`/`EXTER`,
bit 13) either.

However, VERTB is CPU autovector **level 3**, strictly higher priority than
the keyboard's **level 2** (`PORTS`). `lib/keyboard.s`'s `keyb_interrupt`
handler is timing-critical: after reading a scancode it holds the `KDAT`
handshake line active for a hard-coded ~90 microsecond busy-wait (4 raster
lines, polled via `VHPOSR`) before releasing it - this is the real Amiga
keyboard's serial protocol handshake window, not an arbitrary delay. Because
level 3 can **preempt** a lower-priority level 2 handler that is already
running, a VERTB interrupt firing while `keyb_interrupt` is in the middle of
that 90us wait will suspend it for however long the `interrupt` slot chain
takes to run (every declared slot, including any blitter `WAITBLIT` busy-waits)
before `keyb_interrupt` resumes - extending the `KDAT` hold time well past
the protocol's expected window. This can desync or drop keyboard input,
and is more likely to matter the longer your `interrupt` slot bodies run
(e.g. a full-screen blitter clear, or many `SetPixel` calls accumulated
across all active slots) than for a trivial slot body.
This is an inherent consequence of the fixed 68000 hardware priority order
(VERTB=IPL3 > PORTS=IPL2) - it cannot be fixed from the `interrupt` feature
side. Keep slot bodies as short as practical if you also rely on
`GetKey()`/`InitKeyboard()` for input.

**Timing budget rule**: at 7.09 MHz (PAL) each SetPixel call (lores 5-plane)
costs roughly 2,000 cycles from inside an `interrupt` slot (~3 `mulu.w` per
plane × 5 planes plus call-site argument setup). The keyboard ACK window is
638 cycles (90 µs). **The critical figure is the cumulative duration of all
active slots combined** - not each slot individually. 14 slots each doing 32
SetPixels = 448 calls × ~2,000 cycles ≈ 133 ms per VBlank ISR, which delays
every keyboard ACK by ~1,500× the allowed window. The correct fix is the
**VBL-sync flag pattern**: keep slot bodies to pure state updates
(arithmetic, pointer swaps, flag sets) and do all rendering in the main loop
where CPU priority is 0 and keyboard interrupts can fire freely. See
`examples/games/interrupt_16slots_demo.has` for the reference implementation.

## Blitter/graphics operations inside `interrupt` slots

The rule is **not** "never touch the blitter/graphics from an `interrupt`
slot" - it's **"never block for a long time inside one"**. Cheap, register-
level operations (`SetPixel`, updating a copper pointer, swapping a sprite
pointer) take microseconds and are fine. What's dangerous is anything that
**busy-waits**, because the CPU stays at VERTB's interrupt priority (3) for
however long the wait takes - and while it's there, it can't service the
keyboard's level-2 IRQ (or anything else at level 2 or 1).

The concrete example that bit `examples/games/interrupt_bounce_demo.has`
and `interrupt_16slots_demo.has` originally: `ClearScreen()` (lores path)
spins in `WAITBLIT` for a full 320x256 clear - on the order of a few
milliseconds. Doing that every single VBlank, forever, means the CPU spends
a large fraction of every 20ms frame at priority 3, which reliably collides
with the keyboard's ~90us handshake window sooner or later. The fix for `interrupt_bounce_demo.has` (one slot): erase only the ball's
own pixels before redrawing - no blitter, no wait. For
`interrupt_16slots_demo.has` (14 ball slots), even 32 SetPixels per slot is
too much in aggregate: the correct fix is the VBL-sync flag pattern - slot
bodies do physics only (~150 cycles each), rendering happens in the main loop.

If you genuinely need a full-frame blitter operation every VBlank (real
games often do, for double-buffered background redraws), the standard
Amiga technique is to **kick the blit and return without waiting for it to
finish** (don't call the blocking `WAITBLIT`-style helper inside the slot),
then confirm/wait for completion at the very start of the *next* frame's
slot instead - this keeps any single `interrupt` slot's own execution time
short, even though the blit itself takes a while in the background.

Practical checklist for `interrupt` slot bodies:

- For programs that combine rendering with `GetKey()`/`InitKeyboard()` input,
  prefer the VBL-sync flag pattern: one trivial slot sets a flag/counter;
  all SetPixel and blitter work runs in the main loop after a VBL wait at
  IPL 0. See `examples/games/interrupt_16slots_demo.has`.
- Prefer many small, targeted SetPixel/pointer-swap style updates inside slots
  only when the **total** duration across all active slots stays well under
  one frame. One slot doing 32 SetPixels ≈ 9.5 ms; 14 slots ≈ 133 ms.
- Avoid any `WAITBLIT`-style busy-wait loop inside a slot if the program
  also needs reliable keyboard/joystick/serial (level 1-2) interrupt input.
- If a slot must kick a large blit, don't block on its completion in the
  same slot - kick it and check next frame.
- When in doubt, measure: a slot that takes "a while" every single VBlank,
  forever, is far riskier than one that occasionally takes a while once.

## FramePending idiom (optional)

`WaitVBlank` in `lib/helpers.s` busy-polls beam position (PAL line 303). For
a decoupled main loop (logic once per vertical blank, without spinning on
`VPOSR` in the mainline), use one interrupt slot as a frame gate:

```has
extern var frame_pending: int;

interrupt vbl_gate(0) {
    frame_pending = 1;
}

; after TakeSystem + starti(0):
while (quit == 0) {
    while (frame_pending == 0) { /* spin at IPL 0 */ }
    frame_pending = 0;
    ; one frame of game logic / draw here
}
```

This mirrors the AGE `FramePending` / `MainLoop` pattern while staying inside
HAS `interrupt` + `a5 = CUSTOM` conventions. Keep the slot body tiny (flag
only); do blits and `GetKey` work in the main loop.

## Restrictions

- No parameters (only the mandatory `(INDEX)` slot number).
- Must return `void`; `return <expr>;` inside an `interrupt` proc is a
  **compile error** (not just a warning, unlike a normal `void` proc).
- `starti(X)`/`endi(X)` with an out-of-range (`X` not in 0-15) or undeclared
  index is a compile error.
- Slot indices and names must be unique across the program.
- Interrupt procs cannot be `call`ed directly (they're not registered as
  normal callable procs) - they only run via the VBlank dispatcher.
