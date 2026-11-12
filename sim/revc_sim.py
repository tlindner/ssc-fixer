"""Simulate the rev C GAL (revc/sscfixc.pld) at 1 ns resolution.

The registered equations are parsed straight from the .pld file, so this tests the
exact logic that gets programmed. Cart side: CLK = E' xor QX through the SSC's LS86s.
"""
import os, random, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLD = os.path.join(HERE, '..', 'revc', 'sscfixc.pld')

T_CO = 10      # GAL clock-to-output (ATF16V8B-15: 10 ns max)
T_PD = 15      # GAL combinational delay (ATF16V8B-15: 15 ns max)
T_LS86 = 15    # cart LS86 delay per gate

def parse_pld(path):
    text = open(path).read().split('DESCRIPTION')[0]
    text = re.sub(r';[^\n]*', '', text)
    reg, comb = {}, {}
    for m in re.finditer(r'(\w+)(\.R)?\s*=\s*(.*?)(?=\n\s*\w+(?:\.R)?\s*=|\Z)', text, re.S):
        terms = []
        for term in m.group(3).split('+'):
            lits = [l.strip() for l in term.split('*') if l.strip()]
            terms.append([(l.lstrip('/'), l.startswith('/')) for l in lits])
        (reg if m.group(2) else comb)[m.group(1)] = terms
    return reg, comb

EQS, COMB = parse_pld(PLD)
REGS = list(EQS)

def sop(terms, env):
    return int(any(all(env[n] ^ neg for n, neg in t) for t in terms))

def evaluate(state, inputs):
    env = {**state, **inputs}
    return {r: sop(EQS[r], env) for r in REGS}

def waves(cycles, qskew=0):
    E, Q = [], []
    for c in cycles:
        p = 279.4 if c == 'F' else 558.7
        q = p / 2 + qskew
        for t in range(int(round(2 * p))):
            E.append(1 if t >= p else 0)
            Q.append(1 if (q <= t < p + q) else 0)
    return E, Q

def delay(sig, d):
    return [sig[0]] * d + sig[:-d]

def run(cycles, phase, osc_mhz=28.63636, qskew=0):
    E, Q = waves(cycles, qskew)
    N = len(E)
    state = {r: 0 for r in REGS}       # internal (next) register values
    pins = dict(state)                 # register outputs as seen after T_CO
    raw = [0] * N
    period = 1000.0 / osc_mhz
    nxt = phase
    pending = None
    for t in range(N):
        if t >= nxt:
            nxt += period
            state = evaluate(pins, {'E': E[t], 'Q': Q[t]})
            pending = (t + T_CO, dict(state))
        if pending and t >= pending[0]:
            pins = pending[1]; pending = None
        raw[t] = sop(COMB['QX'], {**pins, 'E': E[t], 'Q': Q[t]})
    qx = delay(raw, T_PD)
    Ep = delay(E, T_LS86)
    return delay([Ep[i] ^ qx[i] for i in range(N)], T_LS86)

def halfperiods(clk, skip=3000):
    e = [i for i in range(skip, len(clk)) if clk[i] != clk[i - 1]]
    return e, [b - a for a, b in zip(e, e[1:])]

random.seed(3)
cases = {
    'slow (0.89 MHz)': ('S' * 40, 0),
    'fast (1.79 MHz)': ('F' * 80, 0),
    'slow -> fast -> slow': ('S' * 20 + 'F' * 40 + 'S' * 20, 0),
    'random per-cycle mix': (''.join(random.choice('SF') for _ in range(160)), 0),
    'mix, Q 25 ns late': (''.join(random.choice('SF') for _ in range(160)), 25),
    'mix, Q 25 ns early': (''.join(random.choice('SF') for _ in range(160)), -25),
}
ok = True
print(f"equations parsed from {os.path.relpath(PLD)}: registered {', '.join(REGS)}; combinational {', '.join(COMB)}")
for name, (cyc, sk) in cases.items():
    ws = []
    for ph in range(0, 35, 3):
        e, w = halfperiods(run(cyc, ph, qskew=sk))
        ws += w
    f = (len(e) - 1) / 2 / (e[-1] - e[0]) * 1000
    good = min(ws) >= 200
    ok &= good
    print(f"{name:24s} half-period {min(ws):4d}..{max(ws):4d} ns  avg {f:.3f} MHz  {'PASS' if good else 'FAIL'}")
print('PASS' if ok else 'FAIL')
sys.exit(0 if ok else 1)
