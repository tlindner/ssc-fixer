# SSC Clock Fixer, rev B: bus bridge for CoCo E up to 4 MHz

Rev A ([DESIGN.md](DESIGN.md)) works by substituting Q. That trick only works while
E ≤ 1.79 MHz: above that speed, the SSC's clock would have to cancel E edges, which
causes glitches. Rev B takes a different approach. **It gives the unmodified SSC its
own private bus running at stock speed** (E = 0.895 MHz, CLK = 1.79 MHz), and bridges
the CoCo's accesses to it through a small FIFO. Rev B uses only 74HCT logic: no CPLD,
GAL or microcontroller.

What rev B gives you:

* The CoCo's E can be anything from 0.89 MHz to 4 MHz (and probably more). Speed can
  change on every cycle, as in the SAM's address-dependent mode, a CoCo 3 at 1.79 MHz,
  or a 6309 accelerator running at 4 MHz.
* The PIC and AY always run at exactly 1.7898 MHz.
* The −5 V converter (Q1/L1) runs at its stock 0.895 MHz again. This removes the main
  caveat from rev A.
* The cartridge's own bus decode never sees a fast cycle. At 4 MHz, the stock SSC
  would also fail on bus timing: its '273 latches the data byte at the **start** of
  E-high, before a fast CPU's write data is valid.

## 1. What the SSC does on its bus (schematic page 17)

| CPU access | SSC decode | Effect in the SSC |
|---|---|---|
| Write `$FF7E` | IC2 Y4 | IC9 '273 latches D0–D7 at E↑. IC4a sets: INT3 to the PIC, status D7 = 0 (busy). |
| Write `$FF7D` | IC2 Y2 | IC4b ← D0. This drives the PIC/AY reset (through IC3 with the bus RESET). |
| Read `$FF7E` | IC2 Y5 | IC12 '367 drives D5, D6, D7 (D7 = IC4a /Q: 1 = ready). Reads have no side effects. |

The decoder's address match is A2–A6 = 1, A8–A15 = 1 (IC6 LS133) and A7 = 0. The
PIC clears IC4a through C7 after it reads the latch.

## 2. Architecture

```
 CoCo bus (any speed ≤ 4 MHz)                      │  private SSC bus (0.895 MHz, fixed)
                                                    │
 A0-A15,R/W ─► U2,U3 '688 ─► U4 '138 ─┬─ /W7D,/W7E ─► WSEL ─┐
                                      └─ /R7E ────────────┐ │
 D0-D7 ──────► U5 '574  (clk: E↓) ──── 8 bits ─┐          │ │
 A1 ─────────► U6b      (clk: E↓) ──── A1L ────┤          │ │
               U6a WRF  (clk: E↓, D=WSEL)      │          │ │
                    │                          ▼          │ │
                    └── SI = WRF·E ──► U7,U8,U9 FIFO 16×9 ─┼─┼─► D0_c-D7_c (OE = WC)
                                              │  OR, A1f ─┼─┼─► sequencer
 D5-D7 ◄── U17 '125 ◄── U11 '377 status ◄─────┼──────────┘ │   (U10 WC flip-flop)
           (OE = /R7E + /E)  (clk: Q_c↓, en: read)          │      │
           D7 = RDY·/OR·/WRF                                │      ├─► R/W_c, A0_c, A1_c
                                                            │      └─► SO = WC·/E_c·/Q_c
 X1 3.579545 MHz ─► U1 Johnson counter ─► E_c, Q_c (quadrature, 0.895 MHz)
```

### Per-cycle operation of the private bus

U1 steps through four 279 ns states each cycle: **t1** (Q_c↑), **t2** (E_c↑),
**t3** (Q_c↓), **t0** (E_c↓). At every t1, U10 decides what the cycle will be:

| Condition at t1 | Cycle | Bus |
|---|---|---|
| FIFO has a word (OR = 1) **and** (word is a `$FF7D` write **or** RDY = 1) | **Write** | R/W_c = 0, A1_c/A0_c from the word, data from the FIFO (OE on). SO pulses in t0 to pop the word. |
| Otherwise | **Status read** of `$FF7E` | R/W_c = 1, A1_c = 1, A0_c = 0. U11 captures D5–D7 at t3, so RDY = D7. |

The private bus also runs these rules:

* **Flow control is on the SSC side.** A `$FF7E` byte is only replayed when the last
  status read showed the PIC ready. During t0 of a write cycle, SO holds OR low, so
  a write is always followed by at least one status read. That read sees IC4a busy.
  The SSC latch can therefore never be overwritten, however fast the CPU writes.
* **Order is preserved.** `$FF7D` and `$FF7E` writes share one FIFO, so a reset pulse
  (`STA $FF7D` with 1, then `CLR $FF7D`) keeps its place relative to the data bytes.
  The two writes are never merged.
* **Status as the CPU sees it.** D7 = RDY · FIFO-empty · no-capture-in-flight. Right
  after a write, the CPU sees "busy", just as with the stock cartridge. D5 and D6 are
  the cached values, at most about 2 µs old.

## 3. Circuit

**All logic is 74HCT.** The CoCo bus is TTL-level: NMOS 6809/SAM outputs are only
guaranteed to reach 2.4 V, which is below a 74HC input's 3.15 V threshold.

### Parts

| Ref | Part | Function |
|---|---|---|
| X1 | 3.579545 MHz 5 V can oscillator | Private bus timebase |
| U1 | 74HCT74 | Johnson counter → Q_c (1Q), E_c (2Q) |
| U2 | 74HCT688 | A8–A15 = $FF |
| U3 | 74HCT688 | A7–A2 = 0,1,1,1,1,1 |
| U4 | 74HCT138 | /W7D, /W7E, /R7E (**not** gated by E) |
| U5 | 74HCT574 | CPU write data, captured at E↓ |
| U6 | 74HCT74 | a: WRF (write captured), b: A1L |
| U7, U8, U9 | CD74HCT40105 | 16 × 4 FIFO ×3 = 16 × 12 (9 bits used) |
| U10 | 74HCT74 | a: WC (sequencer), b: spare |
| U11 | 74HCT377 | Status cache D5–D7 (RDY = D7) |
| U12 | 74HCT00 | Glue |
| U13 | 74HCT04 | Glue |
| U14 | 74HCT08 | Glue |
| U15 | 74HCT32 | Glue |
| U16 | 74HCT11 | Glue |
| U17 | 74HCT125 | Status to CoCo D5–D7 |
| RN1 | 8 × 10 kΩ SIP | Pull-ups on the private data bus D0_c–D7_c |
| C | 0.1 µF per IC, 10 µF bulk | Decoupling |
| J1 / J2 | Card-edge plug / socket | As in rev A |

### Connectors

| Pin(s) | J1 (CoCo) | J2 (SSC) |
|---|---|---|
| 6 E | → U13-1, U14-2 | ← E_c (U1-9) |
| 7 Q | not used | ← Q_c (U1-5) |
| 18 R/W | → U4-1 | ← /WC (U10-6) |
| 19 A0 | → U4-2 | ← A0_c (U14-6) |
| 20 A1 | → U4-3, U6-12 | ← A1_c (U15-6) |
| 21–25 A2–A6 | → U3 P0–P4 | +5 V |
| 26 A7 | → U3 P5 | GND |
| 27–31, 37–39 A8–A15 | → U2 P0–P7 | +5 V |
| 10–17 D0–D7 | → U5 D0–D7; D5–D7 ← U17 | ↔ D0_c–D7_c (U7/U8 Q, RN1, U11) |
| 5 RESET, 35 SND, 9 +5 V, 33/34 GND | ↔ J2 | ↔ J1 |
| 1, 2, 3, 4, 8, 32, 36, 40 | ↔ J2 (NC on the SSC) | ↔ J1 |

The '138 enable is tied high (U4-6 = +5 V), so the decode follows address and R/W
only. E is applied afterwards, in the SI and OE_st gates.

### Netlist (pin numbers)

| Net | Connections |
|---|---|
| OSC | X1-8 → U1-3, U1-11 |
| Q_c | U1-5 → U1-12, U10-3 (WC clk), J2-7 |
| /Q_c | U1-6 → U11-11 (status clk), U16-11 |
| E_c | U1-9 → J2-6 |
| /E_c | U1-8 → U1-2, U16-10 |
| U1 PRE/CLR | U1-1, 4, 10, 13 → +5 V |
| /EQH | U2-19 → U4-4. U2: P0–P7 (2,4,6,8,11,13,15,17) = A8–A15. Q0–Q7 (3,5,…,18) = +5 V. /G (1) = GND |
| /EQL | U3-19 → U4-5. U3: P0–P5 = A2–A7. Q0–Q4 = +5 V, Q5 = GND. P6, P7, Q6, Q7 = GND. /G = GND |
| U4 | A (1) = R/W, B (2) = A0, C (3) = A1, G1 (6) = +5 V |
| /W7D | U4-13 → U12-1 |
| /W7E | U4-11 → U12-2 |
| /R7E | U4-10 → U15-1 |
| WSEL | U12-3 → U6-2 |
| E (CoCo) | J1-6 → U13-1, U14-2 |
| /E | U13-2 → U5-11, U6-3, U6-11, U15-2 |
| WRF | U6-5 → U14-1. /WRF: U6-6 → U16-5 |
| A1L | U6-9 → U9-4 (D0) |
| U5 | D0–D7 (2–9) = J1 D0–D7. /OE (1) = GND. Q0–Q3 (19–16) → U7-4…7. Q4–Q7 (15–12) → U8-4…7 |
| SI | U14-3 → U7-3, U8-3, U9-3 |
| SO | U16-8 → U7-15, U8-15, U9-15 |
| MR | U13-8 (from J1-5 RESET at U13-9) → U7-9, U8-9, U9-9 |
| OR | U9-14 → U14-10, U13-11 |
| /OR | U13-10 → U16-4 |
| A1f | U9-13 (Q0) → U12-4, U13-3, U15-5 |
| /A1f | U13-4 → U14-5 |
| FIFO OE | U7-1, U8-1 ← WC. U9-1 = +5 V. U9-5…7 (D1–D3) = GND |
| D0_c–D7_c | U7-13,12,11,10 / U8-13,12,11,10 → J2-10…17. RN1 to +5 V. D5_c, D6_c, D7_c → U11-14, 17, 18 |
| RDY | U11-19 (Q7) → U16-3, U13-5 |
| /RDY | U13-6 → U12-5 |
| X | U12-6 → U14-9 |
| WC_D | U14-8 → U10-2 |
| WC | U10-5 → U7-1, U8-1, U11-1 (/CE: capture on read cycles only), U14-4, U16-9 |
| /WC | U10-6 → J2-18 (R/W_c), U15-4 |
| U10 | /CLR (1) = J1-5 RESET. /PRE (4) = +5 V |
| A0_c | U14-6 → J2-19 |
| A1_c | U15-6 → J2-20 |
| ST5, ST6 | U11-15, U11-16 → U17-2, U17-5 |
| D7_out | U16-6 → U17-9 |
| OE_st | U15-3 → U17-1, 4, 10 |
| U17 out | U17-3 → J1-15 (D5), U17-6 → J1-16 (D6), U17-8 → J1-17 (D7) |

The glue logic, gate by gate:

* WSEL = NAND(/W7D, /W7E)
* X = NAND(A1f, /RDY)
* WC_D = OR · X. This makes a write cycle when the FIFO has a word and the word is either a `$FF7D` write or RDY = 1.
* SI = WRF · E
* A0_c = WC · /A1f
* A1_c = /WC + A1f
* OE_st = /R7E + /E (active low)
* D7_out = RDY · /OR · /WRF
* SO = WC · /E_c · /Q_c

Unused inputs: tie all spare gate inputs and U11's unused D inputs to GND. Tie U10b's
PRE/CLR to +5 V. Disable U17's fourth buffer (pin 13 to +5 V, pin 12 to GND).

## 4. Timing at 4 MHz (E-high = 125 ns)

* **Write capture:** U5 and U6 clock on E↓ through one inverter (about 10 ns). The
  6809/6309 holds write data at least 20 ns after E↓, and the HCT574 needs about
  5 ns hold. WSEL comes from address and R/W only, which are stable well before E↓.
* **SI** is high for the whole E-high of the following CPU cycle. U5 and U6 do not
  change until the next E↓, so the FIFO input is stable throughout.
* **Status read:** OE_st falls about 15 ns after E↑, and U17 drives about 20 ns later.
  That leaves about 90 ns before E↓, against a CPU setup requirement of about 20–40 ns.
* **Private bus:** Address, R/W and data change only at t1. That is 279 ns before
  E_c↑ (when the '273 latches) and 279 ns after the previous E_c↓. This is the same
  margin the stock SSC has with a 0.89 MHz CoCo.
* **Clock domains:** OR crosses into the cart domain. It is sampled by U10 at Q_c↑,
  and the result is not used by the SSC until E_c↑, 279 ns later, which leaves ample
  time for metastability to settle. RDY and OR cross back into D7_out. A flag that
  changes during a CPU read can only give one stale poll, and every stale state is
  "busy", which is the safe direction.

## 5. Simulation

[sim/bridge_sim.py](sim/bridge_sim.py) is an event-level model of this circuit and of
the SSC's latch and busy logic. Each run has a driver that polls D7 before every data
byte and sometimes issues back-to-back `$FF7D` reset pulses. The PIC takes 3–40 µs to
take each byte, and FIFO fall-through is randomized between 80 and 400 ns.

| CPU speed | Runs | Result | Max FIFO depth |
|---|---|---|---|
| 0.89 MHz | 20 × 400 bytes | Pass | 2 |
| 1.79 MHz | 20 × 400 bytes | Pass | 3 |
| 4.0 MHz | 20 × 400 bytes | Pass | 4 |
| Per-cycle random mix | 20 × 400 bytes | Pass | 3 |

"Pass" means three things: every byte reached the PIC in order, no unread byte was
overwritten, and the `$FF7D` and `$FF7E` replay order matched the CPU's order exactly.
To check the checks, removing the RDY term from the sequencer produces 139 overwrite
errors in one 4 MHz run.

## 6. Caveats and things to verify on the bench

1. **CD74HCT40105 details.** The netlist assumes the TI pinout, that data loads on SI
   rising, that OR drops while SO is high, and that the next word appears after SO
   falls. Check all of this against the datasheet before laying out the board. U9's
   flags stand in for all three FIFOs, since they shift in lockstep. If you are
   cautious, AND the three OR outputs together.
2. **Reset pulse width.** Back-to-back `$FF7D` writes are replayed about 2.2 µs apart,
   which is about 4 PIC clocks. On a stock 0.89 MHz CoCo the same code makes a pulse
   of about 8 µs. If the PIC does not reset reliably, add a hold-off after `$FF7D`
   replays. A 74HCT161 that forces 8–16 read cycles would do it.
3. **Software that writes without polling.** Such code relied on 0.89 MHz timing, so
   it already fails on a fast stock machine. Here, its bytes queue in the 16-deep FIFO
   and are delivered at the PIC's pace. Writing more than 16 bytes ahead overflows
   the FIFO.
4. **D5/D6 latency.** These status bits are up to about 2 µs old. That is irrelevant
   to polling loops, but noted for completeness.
5. **Cost and size.** 17 ICs plus the oscillator, roughly $12–18 in parts per unit at
   qty 50, plus the PCB and connectors. The board will be about twice the size of rev A.
6. **Q from the CoCo (J1-7) is not used.** The SSC now gets Q_c from U1.
