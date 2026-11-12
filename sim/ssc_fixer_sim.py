"""1 ns time-step simulation of the SSC clock fixer interposer.

Cart side (unmodified SSC): CLK = E' XOR Qx, where E' = E through IC3 (LS86, pins 12/13 -> 11).
Interposer: Qx = FF output.  FF (74HC74) clocked by Q rising, D = SR Q5,
async /CLR = NAND(E, /Q).  SR = 74HC164 clocked by OSC, /MR = /E, serial in = 1.
"""
import random, sys

OSC_MHZ = 28.63636
T_SR = 18      # HC164 clk->Q
T_FF = 20      # HC74 clk->Q / clr->Q
T_SU = 15      # HC74 setup
T_NAND = 10    # HC00
T_LS86 = 15    # cart LS86 delay (each gate)

def waves(cycles):
    """cycles: list of 'S' (0.894 MHz) or 'F' (1.79 MHz). Returns E,Q arrays at 1 ns."""
    E, Q = [], []
    for c in cycles:
        p = 279.4 if c == 'F' else 558.7     # half period of E
        q = p / 2
        n = int(round(2 * p))
        for t in range(n):
            e = 1 if t >= p else 0                       # cycle starts at E falling
            qq = 1 if (q <= t < p + q) else 0             # Q leads E by 90 deg
            E.append(e); Q.append(qq)
    return E, Q

def delay(sig, d):
    return [sig[0]] * d + sig[:-d] if d else sig[:]

def run(cycles, phase):
    E, Q = waves(cycles)
    N = len(E)
    nE = delay([1 - e for e in E], T_NAND)
    nQ = delay([1 - q for q in Q], T_NAND)
    clr_n = delay([0 if (E[i] and nQ[i]) else 1 for i in range(N)], T_NAND)
    # shift register
    period = 1000.0 / OSC_MHZ
    sr = [0] * 8; srQ5 = [0] * N; pend = []
    next_edge = phase
    for t in range(N):
        if nE[t] == 0:
            sr = [0] * 8
        if t >= next_edge:
            next_edge += period
            if nE[t]:
                sr = [1] + sr[:-1]
        srQ5[t] = sr[5]
    srQ5 = delay(srQ5, T_SR)
    # flip-flop
    ff = 0; ffo = [0] * N
    for t in range(1, N):
        if clr_n[t] == 0:
            ff = 0
        elif Q[t] and not Q[t - 1]:
            ff = srQ5[t - T_SU]   # value that met setup
        ffo[t] = ff
    Qx = delay(ffo, T_FF)
    Ep = delay(E, T_LS86)
    CLK = delay([Ep[i] ^ Qx[i] for i in range(N)], T_LS86)
    return CLK

def pulses(clk, skip=2000):
    edges = [i for i in range(skip, len(clk)) if clk[i] != clk[i - 1]]
    widths = [b - a for a, b in zip(edges, edges[1:])]
    return edges, widths

random.seed(1)
tests = {
    'slow (0.89 MHz)': 'S' * 40,
    'fast (1.79 MHz)': 'F' * 80,
    'switch slow->fast->slow': 'S' * 20 + 'F' * 40 + 'S' * 20,
    'random mix (SAM addr-dependent)': ''.join(random.choice('SF') for _ in range(200)),
}
ok = True
for name, cyc in tests.items():
    allw = []
    for ph in range(0, 35, 5):
        clk = run(cyc, ph)
        e, w = pulses(clk)
        allw += w
        span = e[-1] - e[0]
        freq = (len(e) - 1) / 2 / span * 1000
    mn, mx = min(allw), max(allw)
    print(f"{name:34s} min half-period {mn:4d} ns  max {mx:4d} ns  avg freq {freq:.3f} MHz")
    if mn < 200: ok = False
print("PASS" if ok else "FAIL: pulse narrower than 200 ns")
