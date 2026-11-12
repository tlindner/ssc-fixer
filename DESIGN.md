# SSC Clock Fixer: a cartridge-port interposer

An interposer that plugs into the CoCo cartridge port (or a Multi-Pak slot). The
unmodified Speech/Sound Cartridge plugs into it. With it, the SSC's PIC 7040 and
AY-3-8913 run at 1.79 MHz whether the CPU runs at 0.89 MHz or 1.79 MHz,
including the SAM's address-dependent mode, where speed changes from cycle to cycle.

## 1. Why the SSC runs fast (schematic, pages 17–18)

| Net | Source | Loads |
|---|---|---|
| **E'** | E (pin 6) → IC3 74LS86 pins 12/13 → pin 11 (buffer) | IC2 '138 G1 (bus decode), IC3 pin 10, R16/C26 → Q1 (−5 V converter) |
| **Q** | Q (pin 7) | **only** IC3 pin 9 |
| **CLK** | IC3 pin 8 = E' ⊕ Q | IC8 PIC 7040 CLKIN (pin 17), IC11 AY-3-8913 CLK (pin 20) |

E and Q are in quadrature, so E ⊕ Q has twice the E frequency:

* Normal speed: E = 0.894 MHz → CLK = **1.79 MHz** (as designed)
* Double speed: E = 1.79 MHz → CLK = **3.58 MHz** (the PIC firmware runs twice as fast, and the AY pitches go up an octave)

The SP0256-AL2 has its own 3.12 MHz crystal and is not affected.

The CPU and the PIC exchange data through a mailbox: the IC9 '273 latch, the IC4 '73
handshake flip-flops and the IC12 '367 status buffer. The CPU side of the mailbox uses
only E and the address/data bus, and the PIC side uses only CLK. Fixing CLK alone is
enough. Nothing on the bus side needs to change.

## 2. The idea

E must stay untouched, because the address decode and the −5 V converter use it. But
**Q is used for nothing except making CLK**, so the interposer replaces Q with a
synthesized signal **Qx**. The cartridge still computes CLK = E' ⊕ Qx.

* **Slow cycle:** Qx = Q, so CLK = E ⊕ Q = 1.79 MHz, the original behaviour.
* **Fast cycle:** Qx = 0, so CLK = E' = 1.79 MHz.

Qx only changes while Q is low, and its edges are about 140–280 ns away from any E
edge. The XOR in the cartridge therefore never sees E' and Qx switch at the same
time, so the swap cannot cause glitches.

The interposer decides between slow and fast **on every cycle** by timing how long E
has been low when Q rises:

| Mode | E↓ → Q↑ |
|---|---|
| Fast (1.79 MHz) | ≈ 140 ns |
| Slow (0.89 MHz) | ≈ 279 ns |

The threshold is about 200 ns. A 74HC164 clocked from a 28.636 MHz can oscillator
measures the time, which avoids RC one-shots and needs no trimming.

## 3. Circuit

```
                       CoCo side (male edge)            SSC side (female socket)
 All pins except 7 ─────────────────────────────────────────────── straight through
 pin 6  E  ──┬──────────────────────────────────────────────────── pin 6  E
             │
 pin 7  Q  ──┼──┬───────────────────┐                     (pin 7 NOT passed through)
             │  │                   │
             │  │    U1 74HC00      │
             │  │   ┌──────┐        │
             ├──┼───┤1     │        │
             ├──┼───┤2  3  ├──/E ───┼─────────────┐
             │  ├───┤4     │        │             │
             │  └───┤5  6  ├──/Q ─┐ │             │
             │      │      │      │ │             │
             └──────┤9     │      │ │             │
               /Q ──┤10  8 ├──CLRn┼─┼──────────┐  │
                    └──────┘      │ │          │  │
                                  │ │          │  │
   X1 28.636 MHz   U2 74HC164     │ │          │  │
   ┌────────┐     ┌─────────┐     │ │          │  │
   │ OUT  8 ├─────┤8  CP    │     │ │          │  │
   └────────┘ +5 ─┤1  DSA   │     │ │          │  │
              +5 ─┤2  DSB   │     │ │          │  │
           /E ────┤9  /MR   │     │ │          │  │
   (from U1-3)    │   Q5 11 ├──┐  │ │          │  │
                  └─────────┘  │  │ │          │  │
                               │  │ │  U3A 74HC74 (½)
                               │  │ │  ┌───────────┐
                               └──┼─┼──┤2  D       │
                                  │ └──┤3  CLK     │      R1 47Ω
                                  │    │     Q  5  ├──────/\/\──── pin 7 (Qx) to SSC
                                  │ +5─┤4  /PRE    │
                                  └────┤1  /CLR    │  ← CLRn from U1-8
                                       └───────────┘
   (/Q from U1-6 feeds U1-10. /E from U1-3 feeds U2-9.)
```

### Netlist

| Net | Connections |
|---|---|
| E | CoCo J1-6, SSC J2-6, U1-1, U1-2, U1-9 |
| Q (CoCo) | CoCo J1-7, U1-4, U1-5, U3-3 (CLK) |
| /E | U1-3, U2-9 (/MR) |
| /Q | U1-6, U1-10 |
| CLRn | U1-8, U3-1 (/CLR1) |
| OSC | X1-8 (out), U2-8 (CP) |
| T200 | U2-11 (Q5), U3-2 (D1) |
| Qx | U3-5 (Q1) → R1 47 Ω → SSC J2-7 |
| +5 V | J1-9 ↔ J2-9, U1-14, U2-14, U2-1, U2-2, U3-14, U3-4 (/PRE1), U3-10/13 (/PRE2, /CLR2), X1-14 |
| GND | J1-33/34 ↔ J2-33/34, U1-7, U2-7, U3-7, X1-7, unused inputs U1-12/13, U3-11/12 |
| All other pins | J1-n ↔ J2-n, 1:1 |

**Decoupling:** 0.1 µF at each IC and at the oscillator, plus 10 µF bulk.
**Spare:** U1 gate 4 (pins 11–13) and U3 half B. Tie their inputs to a rail.

### Bill of materials

| Ref | Part | Note |
|---|---|---|
| U1 | 74HC00 | 74HCT00 also works. Use HC/HCT, not LS, so the bus is barely loaded. |
| U2 | 74HC164 | Must handle 28.6 MHz. 74HC is fine at 5 V; 74AC164 or 74ACT164 gives more margin. |
| U3 | 74HC74 | |
| X1 | 28.63636 MHz 5 V full/half-size can oscillator | Standard NTSC ×8 part. 25–32 MHz works if you re-check the stage (see §4). |
| R1 | 47 Ω | Series termination on Qx |
| C1–C4 | 0.1 µF | Decoupling |
| C5 | 10 µF | Bulk |
| J1 | 40-pin 0.1" card-edge **plug** (PCB edge fingers) | To CoCo or MPI |
| J2 | 40-pin 0.1" card-edge **socket** | SSC plugs in |

## 4. Operation and timing

**U2 (timer):** /MR = /E, so the shift register is held clear while E is high. When E
falls it shifts in 1s at 28.636 MHz (34.9 ns per tick). Q5 goes high 6 clock edges
after E↓, at **175–210 ns** (oscillator jitter) plus about 18 ns propagation delay.
Q5 then means: "E has been low for more than about 200 ns".

**U3A (decision latch):** U3A is clocked by the CoCo's Q rising edge and samples Q5:

* Fast cycle: Q↑ at ≈140 ns. Q5 is still 0, so Qx stays 0. Margin is at least 35 ns.
* Slow cycle: Q↑ at ≈279 ns. Q5 is already 1, so Qx goes to 1. Margin is about 35 ns after setup time.

**Clear:** CLRn = NAND(E, /Q) clears U3A while *E is high and Q is low*, which is the
second half of E-high. Qx therefore falls at about Q↓, the same place the real Q would
fall. The clear is released at E↓, about 140–280 ns before the next Q↑ clock edge, so
U3A's recovery time is never violated.

```
Slow cycle (0.89 MHz)                 Fast cycle (1.79 MHz)
E   ‾‾‾\_____________/‾‾‾‾‾‾‾‾‾‾‾‾‾\_   E   ‾\_____/‾‾‾‾‾\_____/‾‾
Q   ______/‾‾‾‾‾‾‾‾‾‾‾‾‾\______/‾‾‾‾‾   Q   ___/‾‾‾‾‾\_____/‾‾‾‾‾\
Q5  ‾‾‾‾\____/‾‾‾‾‾‾‾‾‾‾\______/‾‾‾‾‾   Q5  ‾‾\_____/‾‾‾‾‾\_____/‾
       (0 while E high; 1 ≈200ns after E↓)     (rises ≈200ns, after Q↑)
Qx  ______/‾‾‾‾‾‾‾‾‾‾‾‾‾\______/‾‾‾‾‾   Qx  ______________________  (0)
CLK =E'⊕Qx: 1.79 MHz                    CLK = E': 1.79 MHz
```

**Simulation:** [sim/ssc_fixer_sim.py](sim/ssc_fixer_sim.py) runs at 1 ns resolution
with typical HC/LS delays and sweeps the oscillator phase.

| Case | Min half-period | Max half-period | Avg CLK |
|---|---|---|---|
| All slow | 253 ns | 305 ns | 1.791 MHz |
| All fast | 279 ns | 280 ns | 1.789 MHz |
| Slow → fast → slow | 253 ns | 305 ns | 1.790 MHz |
| Random per-cycle mix (SAM address-dependent) | 253 ns | 305 ns | 1.790 MHz |

No pulse is narrower than 250 ns in any case. Without the fixer, double speed gives
140 ns half-periods.

## 5. Notes and caveats

1. **−5 V supply:** The SSC's −5 V rail for the 2058 op-amps comes from an inductor
   converter, Q1/L1/D4/C7. It is driven from **E'**, which the fixer does not (and
   cannot) change. At double speed the converter switches at twice the rate. C26 is
   marked select-on-test (20–37 pF), so the circuit is somewhat sensitive. **Measure
   the voltage at C7 with the machine in fast mode.** If it sags, the fix is on the
   SSC: either retune C26/R16, or drive R16 from the fixed CLK (IC3 pin 8) instead of E'.
2. **Bus side at 1.79 MHz:** At 1.79 MHz, E-high lasts about 280 ns. The '133 → '138
   decode path into the '273 clock or the '73 flip-flops takes well under 100 ns, so
   the bus side is fine. It never depended on CLK.
3. **Not covered:** "Turbo" mods that run E at 3.58 MHz or faster. Those would be
   seen as "fast" cycles, and CLK would follow E. To support them, add a second
   threshold.
4. **Duty cycle:** CLK is about 45/55 in slow mode (half-periods of 253/305 ns in the simulation) and exactly E's duty in fast mode.
   Both chips accept this.
5. **Layout:** Keep Qx short and next to a ground. Keep the oscillator trace away
   from the edge-connector fingers. The CoCo port carries video-sensitive signals
   on some models, so do not run 28 MHz near pin 35 (SND).
6. **Lower-cost alternative:** Replace X1/U2 with a 74HC123 one-shot triggered on
   E↓, set to about 210 ns, and use its inverted output as D. That saves the
   oscillator, but it needs a trimmer because of RC tolerance at such short widths.
7. **If modifying the SSC is acceptable:** You could skip the interposer: lift IC3
   pin 8 from PIC pin 17 and AY pin 20, then drive both from a 1.7898 MHz oscillator
   (3.579545 MHz ÷ 2). The mailbox is asynchronous, so this works too. The interposer
   exists so the cartridge stays stock.
