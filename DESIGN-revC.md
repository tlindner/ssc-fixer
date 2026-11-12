# SSC Clock Fixer, rev C: one GAL

Rev C does the same job as rev A ([DESIGN.md](DESIGN.md)): it substitutes Q at the
cartridge so the SSC's own `E ⊕ Q` stays at 1.79 MHz. It covers CoCo E of 0.89 MHz
and 1.79 MHz, including speed changes on every cycle in the SAM's address-dependent
mode. It does not cover accelerators above 1.79 MHz; use rev B
([DESIGN-4MHz.md](DESIGN-4MHz.md)) for those.

Rev C replaces rev A's '00, '164 and '74 with a single **ATF16V8B**, Microchip's
in-production GAL16V8. It also keeps the clock more symmetric than rev A:

| | Rev A (3 × 74HC/HCT) | Rev C (1 × ATF16V8B) |
|---|---|---|
| Logic ICs | 3 | 1 |
| Slow-mode CLK half-periods (sim) | 253–305 ns | **270–289 ns** |
| Fast-mode CLK half-periods (sim) | 279–280 ns | 279–280 ns |
| Input levels | Needs HCT for E/Q | GAL inputs are TTL-level natively |
| Tolerated Q phase error | ±35 ns | ±35 ns |
| Change logic without a new board | No | Yes, reprogram it |

## 1. How it works

The idea is the same as rev A:

* **Slow cycle:** QX = Q, so CLK = E ⊕ Q = 1.79 MHz.
* **Fast cycle:** QX = 0, so CLK = E = 1.79 MHz.

The GAL tells slow and fast cycles apart by measuring E↓ → Q↑: 279 ns in slow
cycles, 140 ns in fast ones. Everything runs synchronously from a 28.636 MHz
oscillator (34.9 ns per tick):

1. **Synchronizers.** E1/E2 and Q1/Q2 are two-stage synchronizers that bring E and Q
   into the oscillator's clock domain.
2. **Counter.** C2..C0 is a 3-bit Gray-code counter. It counts while E and Q are both
   low, clears while E is high and Q is low, and holds while Q is high. It saturates
   at state 6 (`101`).
   * Fast cycle: Q freezes it at a count of 4 or 5.
   * Slow cycle: it reaches 6 about 245–290 ns after E↓, about when Q rises.
3. **Output.** QX = Q · (count = 6). This is combinational, so it follows the raw Q
   with only one GAL delay, instead of rev A's flip-flop delay. That is why the
   clock is more symmetric.
4. **No glitches.**
   * Each Gray-code step changes one bit, so the count = 6 decode cannot glitch while
     the counter runs.
   * The only multi-bit change is the clear, and that happens only while Q is
     already low.
   * QX therefore only switches mid-phase, at least 140 ns away from any E edge.

All 8 macrocells are used: 7 registers plus QX.

## 2. Circuit

```
                      U1 ATF16V8B-15
                     ┌──────────────┐
  X1 28.636 MHz ─────┤1 CLK   VCC 20├── +5 V
  CoCo E (J1-6) ──┬──┤2 E      E1 19├── (test point)
  CoCo Q (J1-7) ──┼──┤3 Q      E2 18├── (test point)
         GND ─────┼──┤4-9      Q1 17├── (test point)
                  │  │        Q2 16 ├── (test point)
                  │  │        C0 15 ├── (test point)
                  │  │        C1 14 ├── (test point)
                  │  │        C2 13 ├── (test point)
                  │  │10 GND  QX 12 ├──/\/\/── SSC pin 7 (J2-7)
                  │  │11 /OE─┐      │   47 Ω
                  │  └───────┼──────┘
                  │         GND
                  └──────────────────────────── SSC pin 6 (J2-6), straight through
  All J1 pins except 7 ↔ J2, 1:1
```

### Bill of materials

| Ref | Part | Note |
|---|---|---|
| U1 | ATF16V8B-15PU (DIP-20) or -15JU / -15XU (SMD) | Faster grades (-10, -7) and the ATF16V8C also work. Program with [revc/sscfixc.pld](revc/sscfixc.pld). |
| X1 | 28.63636 MHz 5 V can oscillator | 25–32 MHz works too (see §3) |
| R1 | 47 Ω | Series termination on QX |
| C1, C2 | 0.1 µF | U1 and X1 decoupling |
| C3 | 10 µF | Bulk |
| J1 / J2 | Card-edge plug / socket, or the butt-splice boards | As in rev A |

**Cost at qty 50:** The ATF16V8B is about $1–1.60 and the oscillator about $1.50–3,
so the electronics come to about $3–5 per unit. Most of the cost is still the
card-edge socket, as in rev A.

## 3. Timing margins

The decision depends on how many oscillator ticks fit between E↓ and Q↑. Because
both edges are sampled on the same tick grid, that number is always ⌊t/T⌋ or ⌈t/T⌉:

| Mode | E↓ → Q↑ | Ticks at 28.636 MHz | Decision (threshold 6) |
|---|---|---|---|
| Fast | 140 ns | 4 or 5 | QX stays 0 ✓ |
| Slow | 279 ns | 7 or 8 | Count reaches 6 ✓ |

* **Q phase error.** The decision is still correct if Q is up to about 35 ns early or
  late relative to its nominal quarter-cycle. The simulation checks ±25 ns.
* **Other oscillator frequencies.** The decision needs ⌈140 ns / T⌉ ≤ 5 and
  ⌊279 ns / T⌋ ≥ 6, which allows about 22–35 MHz. The Q phase margin is widest near
  28.6 MHz, so stay within 25–32 MHz to keep reasonable margin.
* **GAL speed.** 28.6 MHz is far below the fMAX of every ATF16V8B grade. The -15
  grade's 15 ns tPD and 10 ns tCO are what the simulation uses.

## 4. Simulation

[sim/revc_sim.py](sim/revc_sim.py) reads the equations **straight out of
`revc/sscfixc.pld`**, so it tests exactly the logic that gets programmed. It runs at
1 ns resolution, sweeps the oscillator phase, and includes the SSC's two LS86 delays.

| Case | CLK half-period | Avg CLK |
|---|---|---|
| Slow (0.89 MHz) | 270–289 ns | 1.791 MHz |
| Fast (1.79 MHz) | 279–280 ns | 1.789 MHz |
| Slow → fast → slow | 270–289 ns | 1.790 MHz |
| Random per-cycle mix | 270–289 ns | 1.790 MHz |
| Mix, Q 25 ns late | 253–305 ns | 1.790 MHz |
| Mix, Q 25 ns early | 255–304 ns | 1.790 MHz |

To check that the test can fail: changing the decode to count = 4 gives 35 ns
pulses, and the simulation reports FAIL.

## 5. Building the JEDEC file

The source is in GALasm syntax:

```bash
galette revc/sscfixc.pld
```

That produces `revc/sscfixc.jed` (GALasm, the original assembler, also works). Burn it
with any programmer that supports the ATF16V8B, such as an XGecu T48 or TL866II+.

Two notes for other tools:

* The JEDEC file has not been generated or checked in yet. Review the fuse map's
  mode bits: registered mode, with pin 12 as a combinational output. Do that before
  building a batch.
* WinCUPL users can transcribe the equations directly. The `.R` suffix becomes `.D`
  with `pin 1 = clock` declared.

## 6. Caveats

1. **−5 V converter.** As in rev A, the converter is still driven by the CoCo's E, so
   it runs at 1.79 MHz in fast mode. Measure C7. Rev B is the only design that
   removes this.
2. **Above 1.79 MHz.** Not supported. An E faster than 1.79 MHz is classed as "fast",
   and CLK simply follows E.
3. **Power-up.** The registers start in an arbitrary state. They resynchronize within
   one E cycle, with at most one irregular clock pulse before the PIC comes out of
   reset.
