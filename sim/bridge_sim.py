"""Event-level simulation of the 4 MHz-capable SSC bus bridge (DESIGN-4MHz.md).

Models, at register level with explicit timing:
  * CoCo side: 6809-style bus cycles at a per-cycle random speed (0.89 / 1.79 / 4.0 MHz,
    or a fixed speed). A driver program polls $FF7E bit 7, writes data bytes to $FF7E,
    and sometimes issues back-to-back reset pulses to $FF7D (1 then 0).
  * Bridge: write capture at CoCo E-fall (U5/U6), SI on the next E-high, a 16-deep FIFO with
    a randomized fall-through time, the WC sequencer clocked on cart Q-rise, SO during
    cart state t0, status cache (U11) captured at cart Q-fall during read cycles, and the
    CPU-visible D7 = RDY & !OR & !WRF.
  * Cart: unmodified SSC behaviour: the '273 latch and IC4a busy flip-flop set at E-rise on
    $FF7E writes, IC4b set from D0 on $FF7D writes, and the PIC clears busy 3-40 us later.

Checks: every byte arrives in order, no byte is overwritten in the SSC latch, every
$FF7D write is replayed in order relative to the data bytes, the FIFO never overflows,
and the cart clock is always exactly 1.79 MHz.
"""
import heapq, random, sys

CART_TICK = 1000 / 3.579545          # ns, one Johnson-counter state
SPEEDS = {'0.89': 1117.3, '1.79': 558.7, '4.0': 250.0}   # CPU cycle length, ns

class Sim:
    def __init__(self, seed, speed_mode, n_bytes=400):
        self.r = random.Random(seed)
        self.speed_mode = speed_mode
        self.q = []; self.seq = 0
        # bridge state
        self.fifo = []            # list of [word, ready_time]
        self.max_fifo = 0
        self.wrf = False; self.cap = None
        self.wc = False; self.wc_word = None
        self.so_pending = False
        self.rdy = True
        # cart state
        self.busy = False; self.latch = None
        self.cart_log = []        # what the cart saw, in order
        self.pic_rx = []
        self.errors = []
        # cpu program
        self.n_bytes = n_bytes
        self.cpu_log = []         # writes the CPU issued, in order
        self.prog = self.program()
        self.done = False

    def at(self, t, fn, *a):
        self.seq += 1; heapq.heappush(self.q, (t, self.seq, fn, a))

    # ---------------- FIFO (HC40105 model) ----------------
    def fifo_or(self, t):
        return bool(self.fifo) and self.fifo[0][1] <= t and not self.so_pending

    def fifo_push(self, t, word):
        if len(self.fifo) >= 16:
            self.errors.append(f"{t:.0f}: FIFO overflow"); return
        # fall-through: a word reaches the output 80-400 ns after SI, never before the one ahead
        ft = t + self.r.uniform(80, 400)
        if self.fifo: ft = max(ft, self.fifo[-1][1])
        self.fifo.append([word, ft])
        self.max_fifo = max(self.max_fifo, len(self.fifo))

    # ---------------- CPU program ----------------
    def program(self):
        """Yields bus ops: ('rd',) / ('wr', addr, data) / ('nop',)"""
        sent = 0
        while sent < self.n_bytes:
            if self.r.random() < 0.05:           # reset pulse: STA $FF7D (1) ; CLR $FF7D (0)
                for _ in range(2): yield ('nop',)
                yield ('wr', 0x7D, 1)
                for _ in range(self.r.choice([0, 1, 3])): yield ('nop',)
                yield ('wr', 0x7D, 0)
            while True:                          # poll: LDA $FF7E ; BPL loop
                d7 = yield ('rd',)
                for _ in range(2): yield ('nop',)
                if d7: break
            for _ in range(self.r.choice([1, 2, 4])): yield ('nop',)
            yield ('wr', 0x7E, sent & 0xFF)
            sent += 1
        self.done = True
        yield ('nop',)

    def cpu_cycle(self, t, op_result=None):
        if self.done: return
        try:
            op = self.prog.send(op_result)
        except StopIteration:
            self.done = True; return
        if self.speed_mode == 'mix':
            T = SPEEDS[self.r.choice(list(SPEEDS))]
        else:
            T = SPEEDS[self.speed_mode]
        e_rise, e_fall = t + T / 2, t + T
        # SI happens during this cycle's E-high if previous cycle captured a write
        if self.wrf:
            self.at(e_rise + 10, self.fifo_push_ev, self.cap)
        self.at(e_fall, self.cpu_e_fall, op)

    def fifo_push_ev(self, t, word):
        self.fifo_push(t, word)

    def cpu_e_fall(self, t, op):
        res = None
        self.wrf = False
        if op[0] == 'wr':
            self.wrf = True; self.cap = (op[1], op[2])
            self.cpu_log.append((op[1], op[2]))
        elif op[0] == 'rd':
            # D7 = RDY & !OR & !WRF  (WRF here = value during this cycle, before update)
            res = self.rdy and not self.fifo_or(t) and not self.prev_wrf
        self.prev_wrf = self.wrf
        self.at(t, lambda tt, rr: self.cpu_cycle(tt, rr), res)

    # ---------------- cart side ----------------
    # Johnson states per cycle: t1 (Q rise) -> t2 (E rise) -> t3 (Q fall) -> t0 (E fall) -> t1
    def cart_t1(self, t):
        self.so_pending = False
        if self.wc_word is not None:   # SO falling edge completes the shift-out
            self.fifo.pop(0)
            if self.fifo: self.fifo[0][1] = max(self.fifo[0][1], t + self.r.uniform(80, 400))
            self.wc_word = None
        orf = self.fifo_or(t)
        self.wc = orf and (self.fifo[0][0][0] == 0x7D or self.rdy)
        if self.wc: self.wc_word = self.fifo[0][0]
        self.at(t + CART_TICK, self.cart_t2)

    def cart_t2(self, t):               # cart E rises: '273 latch + IC4a / IC4b clock
        if self.wc:
            a, d = self.wc_word
            self.cart_log.append((a, d))
            if a == 0x7E:
                if self.busy:
                    self.errors.append(f"{t:.0f}: overwrote unread byte {self.latch}")
                self.latch = d; self.busy = True
                self.at(t + self.r.uniform(3000, 40000), self.pic_read)
        self.at(t + CART_TICK, self.cart_t3)

    def cart_t3(self, t):               # cart Q falls: U11 captures status on read cycles
        if not self.wc:
            self.rdy = not self.busy
        self.at(t + CART_TICK, self.cart_t0)

    def cart_t0(self, t):               # cart E falls: SO high for write cycles
        if self.wc: self.so_pending = True
        self.at(t + CART_TICK, self.cart_t1)

    def pic_read(self, t):
        self.pic_rx.append(self.latch); self.busy = False

    def run(self):
        self.prev_wrf = False
        self.at(0, lambda tt: self.cpu_cycle(tt))
        self.at(self.r.uniform(0, 4 * CART_TICK), self.cart_t1)
        while self.q and not (self.done and len(self.pic_rx) == self.n_bytes and not self.fifo):
            t, _, fn, a = heapq.heappop(self.q)
            if t > 5e8: self.errors.append("timeout"); break
            fn(t, *a)
        exp = [d for a, d in self.cpu_log if a == 0x7E]
        if self.pic_rx != exp:
            self.errors.append("PIC byte stream mismatch")
        if [x for x in self.cart_log] != self.cpu_log[:len(self.cart_log)] or len(self.cart_log) != len(self.cpu_log):
            self.errors.append("cart write order mismatch")
        return t

ok = True
for mode in ['0.89', '1.79', '4.0', 'mix']:
    worst = 0; tot_err = []
    for seed in range(20):
        s = Sim(seed, mode)
        t = s.run()
        worst = max(worst, s.max_fifo)
        tot_err += s.errors
    status = 'PASS' if not tot_err else 'FAIL ' + '; '.join(tot_err[:3])
    ok &= not tot_err
    print(f"CPU {mode:>4} MHz: 20 runs x 400 bytes (+$FF7D pulses)  max FIFO depth {worst:2d}  {status}")
print("cart CLK = Q_c xor E_c from 3.579545 MHz Johnson counter: 1.7898 MHz, fixed")
sys.exit(0 if ok else 1)
