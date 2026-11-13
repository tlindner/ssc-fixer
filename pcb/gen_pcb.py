#!/usr/bin/env python3
"""Generate the rev A SSC Clock Fixer interposer PCB (see DESIGN.md).

Run with KiCad's bundled Python:

  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
      pcb/gen_pcb.py

Board layout (top = SSC socket, bottom = CoCo edge fingers, viewed from F.Cu):

  * J1: 40 edge fingers, odd pins on F.Cu, even pins on B.Cu, pin 1 at left.
  * J2: 2x20 0.1" through-hole card-edge socket; J2-n sits straight above J1-n.
  * Pass-through nets run as fixed lanes: odd pins on F.Cu, even pins on B.Cu.
    Pins 1-6 stay in their columns on the left; pins 8-40 squeeze into a
    0.6 mm-pitch bus on the right, which opens a window in the middle of the
    board on both layers for the SMD logic.
  * The logic (SOIC-14 x3, SMD oscillator, 0805 passives) is routed by a small
    grid maze router into that window. It taps E from its B.Cu lane, +5 V from
    its F.Cu lane, takes Q straight from finger J1-7 and drives J2-7 (Qx).
    GND comes down from J2-34 over the top of the socket.
"""
import heapq
import math
import os
import sys

from array import array
import pcbnew as P

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "ssc-fixer.kicad_pcb")
FPLIB = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"

mm = P.FromMM


def V(x, y):
    return P.VECTOR2I(mm(x), mm(y))


# ---------------------------------------------------------------- geometry
PITCH = 2.54
X0 = 105.87                      # x of J1/J2 column 0 (pins 1/2)
def colx(c):
    return X0 + c * PITCH

BX0, BX1 = 100.0, 160.0          # board body
BY0, BY1 = 100.0, 158.0
TX0, TX1 = 103.33, 156.67        # finger tab (2.1" wide)
TY1 = 168.0                      # board bottom edge (finger tips)

FING_W, FING_L = 1.6, 8.0
FING_CY = TY1 - 0.5 - FING_L / 2  # finger centre y
FING_TOP = TY1 - 0.5 - FING_L     # 159.5
LANE_START = FING_TOP + 1.0       # lanes start inside the finger pad

Y_EVEN = 104.0                   # J2 even row (top)
Y_ODD = Y_EVEN + 5.08            # J2 odd row
SOCK_PAD, SOCK_DRILL = 1.6, 1.0

BUS_P = 0.6                      # compressed bus pitch
TRACK_W = 0.25
PWR_W = 0.4
CLR = 0.2
VIA_D, VIA_DRILL = 0.6, 0.3

board = P.NewBoard(OUT)
ds = board.GetDesignSettings()
ds.SetCopperLayerCount(2)
nc = ds.m_NetSettings.GetDefaultNetclass()
nc.SetClearance(mm(CLR))
nc.SetTrackWidth(mm(TRACK_W))
nc.SetViaDiameter(mm(VIA_D))
nc.SetViaDrill(mm(VIA_DRILL))
ds.m_MinClearance = mm(CLR)
ds.m_TrackMinWidth = mm(0.2)
ds.m_CopperEdgeClearance = mm(0.5)

# ---------------------------------------------------------------- nets
NETS = {}
def net(name):
    if name not in NETS:
        n = P.NETINFO_ITEM(board, name)
        board.Add(n)
        NETS[name] = n
    return NETS[name]

COCO_NAMES = {1: "-12V", 2: "+12V", 3: "HALT", 4: "NMI", 5: "RESET", 6: "E",
              7: "Q_COCO", 8: "CART", 9: "+5V", 10: "D0", 11: "D1", 12: "D2",
              13: "D3", 14: "D4", 15: "D5", 16: "D6", 17: "D7", 18: "R/W",
              19: "A0", 20: "A1", 21: "A2", 22: "A3", 23: "A4", 24: "A5",
              25: "A6", 26: "A7", 27: "A8", 28: "A9", 29: "A10", 30: "A11",
              31: "A12", 32: "CTS", 33: "GND", 34: "GND", 35: "SND",
              36: "SCS", 37: "A13", 38: "A14", 39: "A15", 40: "SLENB"}
def j1net(p):
    return COCO_NAMES[p]
def j2net(p):
    return "QX" if p == 7 else COCO_NAMES[p]

# ---------------------------------------------------------------- footprints
def add_text(fp_or_board, text, x, y, layer=P.F_SilkS, size=1.0, parent=None):
    t = P.PCB_TEXT(board)
    t.SetText(text)
    t.SetPosition(V(x, y))
    t.SetLayer(layer)
    t.SetTextSize(V(size, size))
    t.SetTextThickness(mm(size * 0.15))
    if layer in (P.B_SilkS,):
        t.SetMirrored(True)
    board.Add(t)
    return t


def lset(*layers):
    s = P.LSET()
    for l in layers:
        s.AddLayer(l)
    return s


def make_fingers():
    fp = P.FOOTPRINT(board)
    fp.SetReference("J1")
    fp.SetValue("CoCo cartridge edge 2x20 P2.54")
    fp.SetFPID(P.LIB_ID("ssc-fixer", "CoCo_Edge_2x20_P2.54mm"))
    fp.SetAttributes(P.FP_SMD | P.FP_EXCLUDE_FROM_POS_FILES)
    board.Add(fp)
    fp.SetPosition(V(130.0, FING_CY))
    for p in range(1, 41):
        c = (p - 1) // 2
        pad = P.PAD(fp)
        pad.SetNumber(str(p))
        pad.SetShape(P.PAD_SHAPE_RECT)
        pad.SetAttribute(P.PAD_ATTRIB_CONN)
        pad.SetSize(V(FING_W, FING_L))
        if p % 2:
            pad.SetLayerSet(lset(P.F_Cu, P.F_Mask))
        else:
            pad.SetLayerSet(lset(P.B_Cu, P.B_Mask))
        fp.Add(pad)
        pad.SetPosition(V(colx(c), FING_CY))
        pad.SetNet(net(j1net(p)))
    fp.Reference().SetPosition(V(TX0 - 1.5, 150))
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    fp.Value().SetLayer(P.F_Fab)
    return fp


def make_socket():
    fp = P.FOOTPRINT(board)
    fp.SetReference("J2")
    fp.SetValue("40-pin 0.1in card-edge socket, rows 0.2in")
    fp.SetFPID(P.LIB_ID("ssc-fixer", "CardEdge_Socket_2x20_P2.54mm_Row5.08mm"))
    fp.SetAttributes(P.FP_THROUGH_HOLE)
    board.Add(fp)
    fp.SetPosition(V(130.0, (Y_ODD + Y_EVEN) / 2))
    for p in range(1, 41):
        c = (p - 1) // 2
        pad = P.PAD(fp)
        pad.SetNumber(str(p))
        pad.SetShape(P.PAD_SHAPE_RECT if p == 1 else P.PAD_SHAPE_CIRCLE)
        pad.SetAttribute(P.PAD_ATTRIB_PTH)
        pad.SetSize(V(SOCK_PAD, SOCK_PAD))
        pad.SetDrillSize(V(SOCK_DRILL, SOCK_DRILL))
        pad.SetLayerSet(P.PAD.PTHMask())
        fp.Add(pad)
        pad.SetPosition(V(colx(c), Y_ODD if p % 2 else Y_EVEN))
        pad.SetNet(net(j2net(p)))
    # socket body outline on silk + courtyard (approximate; check the datasheet)
    x0, x1 = colx(0) - 3.5, colx(19) + 3.5
    y0, y1 = Y_EVEN - 2.6, Y_ODD + 2.6
    for layer, grow in ((P.F_SilkS, 0.0), (P.F_CrtYd, 0.25), (P.F_Fab, 0.0)):
        r = P.PCB_SHAPE(fp)
        r.SetShape(P.SHAPE_T_RECT)
        r.SetStart(V(x0 - grow, y0 - grow))
        r.SetEnd(V(x1 + grow, y1 + grow))
        r.SetLayer(layer)
        r.SetWidth(mm(0.12 if layer != P.F_CrtYd else 0.05))
        fp.Add(r)
    fp.Reference().SetPosition(V(x0 + 1.6, Y_ODD + 1.4))
    fp.Reference().SetTextSize(V(0.8, 0.8))
    fp.Value().SetVisible(False)
    fp.Value().SetLayer(P.F_Fab)
    return fp


def load_fp(lib, name, ref, value, x, y, rot=0):
    fp = P.FootprintLoad(os.path.join(FPLIB, lib + ".pretty"), name)
    fp.SetFPID(P.LIB_ID(lib, name))
    fp.SetReference(ref)
    fp.SetValue(value)
    board.Add(fp)
    fp.SetPosition(V(x, y))
    fp.SetOrientationDegrees(rot)
    return fp


def connect(fp, pinmap):
    for pad in fp.Pads():
        n = pinmap.get(pad.GetNumber())
        if n:
            pad.SetNet(net(n))


J1 = make_fingers()
J2 = make_socket()

SOIC = ("Package_SO", "SOIC-14_3.9x8.7mm_P1.27mm")
U3 = load_fp(*SOIC, "U3", "74HCT74", 122.5, 128.5)
U1 = load_fp(*SOIC, "U1", "74HCT00", 122.5, 141.5)
U2 = load_fp(*SOIC, "U2", "74HC164", 133.5, 134.0)
X1 = load_fp("Oscillator", "Oscillator_SMD_EuroQuartz_XO53-4Pin_5.0x3.2mm",
             "X1", "28.63636MHz", 136.0, 144.5)
R1 = load_fp("Resistor_SMD", "R_0805_2012Metric", "R1", "47", 116.4, 125.0, 90)
C1 = load_fp("Capacitor_SMD", "C_0805_2012Metric", "C1", "100n", 128.5, 141.5, 90)
C2 = load_fp("Capacitor_SMD", "C_0805_2012Metric", "C2", "100n", 139.5, 133.0, 90)
C3 = load_fp("Capacitor_SMD", "C_0805_2012Metric", "C3", "100n", 128.5, 127.0, 90)
C4 = load_fp("Capacitor_SMD", "C_0805_2012Metric", "C4", "100n", 141.5, 144.5, 90)
C5 = load_fp("Capacitor_SMD", "C_1206_3216Metric", "C5", "10u", 141.0, 126.5, 90)

connect(U1, {"1": "E", "2": "E", "3": "/E", "4": "Q_COCO", "5": "Q_COCO",
             "6": "/Q", "7": "GND", "8": "CLRn", "9": "E", "10": "/Q",
             "12": "GND", "13": "GND", "14": "+5V"})
connect(U2, {"1": "+5V", "2": "+5V", "7": "GND", "8": "OSC", "9": "/E",
             "11": "T200", "14": "+5V"})
connect(U3, {"1": "CLRn", "2": "T200", "3": "Q_COCO", "4": "+5V",
             "5": "QX_INT", "7": "GND", "10": "+5V", "11": "GND",
             "12": "GND", "13": "+5V", "14": "+5V"})
connect(X1, {"1": "+5V", "2": "GND", "3": "OSC", "4": "+5V"})
connect(R1, {"1": "QX_INT", "2": "QX"})
for c in (C1, C2, C3, C4, C5):
    connect(c, {"1": "+5V", "2": "GND"})

# ---------------------------------------------------------------- outline
def edge(pts):
    for a, b in zip(pts, pts[1:] + pts[:1]):
        s = P.PCB_SHAPE(board)
        s.SetShape(P.SHAPE_T_SEGMENT)
        s.SetStart(V(*a))
        s.SetEnd(V(*b))
        s.SetLayer(P.Edge_Cuts)
        s.SetWidth(mm(0.1))
        board.Add(s)

OUTLINE = [(BX0, BY0), (BX1, BY0), (BX1, BY1), (TX1, BY1), (TX1, TY1),
           (TX0, TY1), (TX0, BY1), (BX0, BY1)]
edge(OUTLINE)

def inside_board(x, y):
    if BX0 <= x <= BX1 and BY0 <= y <= BY1:
        return True
    return TX0 <= x <= TX1 and BY1 <= y <= TY1

# ---------------------------------------------------------------- fixed lanes
def track(pts, layer, netname, w=TRACK_W):
    out = []
    for a, b in zip(pts, pts[1:]):
        if a == b:
            continue
        t = P.PCB_TRACK(board)
        t.SetStart(V(*a))
        t.SetEnd(V(*b))
        t.SetLayer(layer)
        t.SetWidth(mm(w))
        t.SetNet(net(netname))
        board.Add(t)
        out.append((a, b, layer, netname, w))
    return out

FIXED = []   # (a, b, layer, net, width) for the router's obstacle map

# F.Cu, left group: pins 1, 3, 5 straight up
for p in (1, 3, 5):
    x = colx((p - 1) // 2)
    FIXED += track([(x, LANE_START), (x, Y_ODD)], P.F_Cu, j1net(p))

# B.Cu, left group: pins 2, 4, 6 straight, jog between J2 odd-row pads
def socket_jog_b(x):
    return [(x, Y_ODD + 2.77), (x + 1.27, Y_ODD + 1.5), (x + 1.27, Y_ODD - 1.5),
            (x, Y_ODD - 2.77), (x, Y_EVEN)]
for p in (2, 4, 6):
    x = colx((p - 1) // 2)
    FIXED += track([(x, LANE_START)] + socket_jog_b(x), P.B_Cu, j1net(p))

# F.Cu, right group: odd pins 9..39 (cols 4..19) squeeze right
for k, c in enumerate(range(4, 20)):
    p = 2 * c + 1
    x = colx(c)
    t = colx(19) - (15 - k) * BUS_P
    h = (FING_TOP - 1.5) - (15 - k) * BUS_P
    g = (Y_ODD + 3.0) + (15 - k) * BUS_P
    w = PWR_W if p == 9 else TRACK_W
    FIXED += track([(x, LANE_START), (x, h), (t, h), (t, g), (x, g), (x, Y_ODD)],
                   P.F_Cu, j1net(p), w)
F_WALL = colx(19) - 15 * BUS_P          # +5 V lane x inside the window

# B.Cu, right group: even pins 8..40 (cols 3..19) squeeze right
for k, c in enumerate(range(3, 20)):
    p = 2 * c + 2
    x = colx(c)
    t = colx(19) + 1.27 - (16 - k) * BUS_P
    h = (FING_TOP - 1.5) - (16 - k) * BUS_P
    g = (Y_ODD + 3.0) + (16 - k) * BUS_P
    w = PWR_W if p == 34 else TRACK_W
    FIXED += track([(x, LANE_START), (x, h), (t, h), (t, g), (x + 1.27, g),
                    (x + 1.27, Y_ODD - 1.5), (x, Y_ODD - 2.77), (x, Y_EVEN)],
                   P.B_Cu, j1net(p), w)

# GND feed: J2-34 up over the socket, left, and down between columns 3/4
GX = colx(3) + 1.27
GND_FEED_END = (GX, 123.0)
FIXED += track([(colx(16), Y_EVEN), (colx(16), 101.6), (GX, 101.6), GND_FEED_END],
               P.F_Cu, "GND", PWR_W)

# ---------------------------------------------------------------- maze router
G = 0.1                                   # grid (mm)
GX0, GY0 = BX0, BY0
NX, NY = int(round((BX1 - BX0) / G)) + 1, int(round((TY1 - BY0) / G)) + 1
RCLR = CLR + 0.07                         # router clearance with grid margin
FREE, BLOCK = 0, -1
grid = [array("i", [0]) * (NX * NY) for _ in range(2)]   # owner netcode, -1 blocked
LAYERS = (P.F_Cu, P.B_Cu)

def gi(x):
    return int(round((x - GX0) / G))
def gj(y):
    return int(round((y - GY0) / G))
def gx(i):
    return GX0 + i * G
def gy(j):
    return GY0 + j * G

def gget(li, i, j):
    return grid[li][j * NX + i]

def cells_in(x0, y0, x1, y1):
    i0 = max(0, int(math.floor((x0 - GX0) / G)))
    i1 = min(NX - 1, int(math.ceil((x1 - GX0) / G)))
    j0 = max(0, int(math.floor((y0 - GY0) / G)))
    j1 = min(NY - 1, int(math.ceil((y1 - GY0) / G)))
    return i0, i1, j0, j1

def seg_dist(x, y, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(x - ax, y - ay)
    t = min(1.0, max(0.0, ((x - ax) * dx + (y - ay) * dy) / L2))
    return math.hypot(x - (ax + t * dx), y - (ay + t * dy))

def claim(li, idx, code):
    g = grid[li]
    v = g[idx]
    if v == FREE:
        g[idx] = code
    elif v != code:
        g[idx] = BLOCK

def mark_seg(li, a, b, halfw, code, inflate):
    r = halfw + inflate
    i0, i1, j0, j1 = cells_in(min(a[0], b[0]) - r, min(a[1], b[1]) - r,
                              max(a[0], b[0]) + r, max(a[1], b[1]) + r)
    for j in range(j0, j1 + 1):
        y = GY0 + j * G
        for i in range(i0, i1 + 1):
            if seg_dist(GX0 + i * G, y, a, b) <= r:
                claim(li, j * NX + i, code)

def mark_rect(li, x0, y0, x1, y1, code, inflate):
    i0, i1, j0, j1 = cells_in(x0 - inflate, y0 - inflate, x1 + inflate, y1 + inflate)
    for j in range(j0, j1 + 1):
        y = GY0 + j * G
        dy = max(y0 - y, y - y1, 0)
        for i in range(i0, i1 + 1):
            x = GX0 + i * G
            dx = max(x0 - x, x - x1, 0)
            if math.hypot(dx, dy) <= inflate:
                claim(li, j * NX + i, code)

def mark_circle(li, cx, cy, r, code, inflate):
    mark_seg(li, (cx, cy), (cx, cy), r, code, inflate)

TR_INF = RCLR + TRACK_W / 2          # keep track centres this far from copper

# board edge keep-out
EDGE_KEEP = 0.5 + TRACK_W / 2 + 0.05
def inside_shrunk(x, y, d):
    a = (BX0 + d <= x <= BX1 - d) and (BY0 + d <= y <= BY1 - d)
    b = (TX0 + d <= x <= TX1 - d) and (BY0 + d <= y <= TY1 - d)
    return a or b
for j in range(NY):
    for i in range(NX):
        if not inside_shrunk(GX0 + i * G, GY0 + j * G, EDGE_KEEP):
            grid[0][j * NX + i] = BLOCK
            grid[1][j * NX + i] = BLOCK

PAD_TARGETS = {}   # netcode -> list of (li, (i0, i1, j0, j1), smd, name)
for fp in board.GetFootprints():
    for pad in fp.Pads():
        code = pad.GetNetCode()
        bb = pad.GetBoundingBox()
        x0, y0 = P.ToMM(bb.GetLeft()), P.ToMM(bb.GetTop())
        x1, y1 = P.ToMM(bb.GetRight()), P.ToMM(bb.GetBottom())
        circ = pad.GetAttribute() == P.PAD_ATTRIB_PTH and pad.GetNumber() != "1"
        for li, L in enumerate(LAYERS):
            if not pad.IsOnLayer(L):
                continue
            if circ:
                mark_circle(li, (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2,
                            code or BLOCK, TR_INF)
            else:
                mark_rect(li, x0, y0, x1, y1, code or BLOCK, TR_INF)
            if code:
                s = 0.15
                i0, i1, j0, j1 = cells_in(x0 + s, y0 + s, x1 - s, y1 - s)
                cx, cy, cr = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2 - s
                cs = {(li, i, j) for i in range(i0, i1 + 1) for j in range(j0, j1 + 1)
                      if not circ or math.hypot(gx(i) - cx, gy(j) - cy) <= cr}
                PAD_TARGETS.setdefault(code, []).append(
                    (li, cs,
                     pad.GetAttribute() == P.PAD_ATTRIB_SMD,
                     fp.GetReference() + "-" + pad.GetNumber()))

def code_of(name):
    return NETS[name].GetNetCode()

for a, b, layer, n, w in FIXED:
    mark_seg(LAYERS.index(layer), a, b, w / 2, code_of(n), RCLR + TRACK_W / 2)

# own-net copper the router may connect to (fixed lanes)
LANE_TARGETS = {}
for a, b, layer, n, w in FIXED:
    LANE_TARGETS.setdefault(code_of(n), []).append((LAYERS.index(layer), a, b, w))

VIA_R_CELLS = int(math.ceil((VIA_D / 2 - TRACK_W / 2) / G))
NOVIA = bytearray(NX * NY)      # near SMD pads and connector fingers: no vias
for code, lst in PAD_TARGETS.items():
    for li, cs, smd, _ in lst:
        m = 5 if smd else 9
        i0, i1 = min(c[1] for c in cs), max(c[1] for c in cs)
        j0, j1 = min(c[2] for c in cs), max(c[2] for c in cs)
        for j in range(max(0, j0 - m), min(NY, j1 + m + 1)):
            for i in range(max(0, i0 - m), min(NX, i1 + m + 1)):
                NOVIA[j * NX + i] = 1
for j in range(int((FING_TOP - 1 - GY0) / G), NY):
    for i in range(NX):
        NOVIA[j * NX + i] = 1

def via_ok(code, i, j):
    if NOVIA[j * NX + i]:
        return False
    r = VIA_R_CELLS
    if i - r < 0 or j - r < 0 or i + r >= NX or j + r >= NY:
        return False
    for li in range(2):
        g = grid[li]
        for jj in range(j - r, j + r + 1):
            for ii in range(i - r, i + r + 1):
                v = g[jj * NX + ii]
                if v != FREE and v != code:
                    return False
    return True

DIRS = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
        (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)]
VIA_COST = 40.0
TURN_COST = 2.0
B_PENALTY = 1.15

def astar(code, sources, targets, bbox):
    """sources/targets: sets of (li, i, j). Returns list of states."""
    tset = set(targets)
    tx = [t[1] for t in tset]
    ty = [t[2] for t in tset]
    tbx0, tbx1, tby0, tby1 = min(tx), max(tx), min(ty), max(ty)
    def h(i, j):
        dx = max(tbx0 - i, 0, i - tbx1)
        dy = max(tby0 - j, 0, j - tby1)
        return max(dx, dy) + 0.414 * min(dx, dy)
    ox0, ox1, oy0, oy1 = bbox
    openh = []
    best = {}
    prev = {}
    for s in sources:
        st = (s[0], s[1], s[2], -1)
        best[st] = 0.0
        heapq.heappush(openh, (h(s[1], s[2]), 0.0, st))
    via_memo = {}
    while openh:
        f, g, st = heapq.heappop(openh)
        if g > best.get(st, 1e18):
            continue
        li, i, j, d = st
        if (li, i, j) in tset:
            path = [st]
            while st in prev:
                st = prev[st]
                path.append(st)
            return path[::-1]
        for di, (dx, dy, c) in enumerate(DIRS):
            ni, nj = i + dx, j + dy
            if not (ox0 <= ni <= ox1 and oy0 <= nj <= oy1):
                continue
            v = grid[li][nj * NX + ni]
            if v != FREE and v != code:
                continue
            if dx and dy:   # no corner cutting
                if grid[li][j * NX + ni] not in (FREE, code) or grid[li][nj * NX + i] not in (FREE, code):
                    continue
            ng = g + c * (B_PENALTY if li else 1.0) + (TURN_COST if d not in (-1, di) else 0)
            ns = (li, ni, nj, di)
            if ng < best.get(ns, 1e18):
                best[ns] = ng
                prev[ns] = st
                heapq.heappush(openh, (ng + h(ni, nj), ng, ns))
        ol = 1 - li
        if grid[ol][j * NX + i] in (FREE, code):
            key = (i, j)
            if key not in via_memo:
                via_memo[key] = via_ok(code, i, j)
            if via_memo[key]:
                ng = g + VIA_COST
                ns = (ol, i, j, -1)
                if ng < best.get(ns, 1e18):
                    best[ns] = ng
                    prev[ns] = st
                    heapq.heappush(openh, (ng + h(i, j), ng, ns))
    return None


def lane_cells(li, a, b, w):
    out = set()
    n = int(max(abs(b[0] - a[0]), abs(b[1] - a[1])) / G) + 1
    for k in range(n + 1):
        x = a[0] + (b[0] - a[0]) * k / n
        y = a[1] + (b[1] - a[1]) * k / n
        i, j = gi(x), gj(y)
        if math.hypot(gx(i) - x, gy(j) - y) <= w / 2 - 0.03:
            out.add((li, i, j))
    return out

def pad_cells(entry):
    return set(entry[1])

ROUTED = []
FAILED = []

def emit(code, path, width):
    """Turn a cell path into tracks + vias and mark it in the grid."""
    name = board.FindNet(code).GetNetname()
    segs = []
    start = path[0]
    for a, b in zip(path, path[1:]):
        if a[0] != b[0]:
            v = P.PCB_VIA(board)
            v.SetPosition(V(gx(a[1]), gy(a[2])))
            v.SetWidth(mm(VIA_D))
            v.SetDrill(mm(VIA_DRILL))
            v.SetNet(net(name))
            board.Add(v)
            for li in range(2):
                mark_circle(li, gx(a[1]), gy(a[2]), VIA_D / 2, code, RCLR + TRACK_W / 2)
    # collapse into straight runs per layer
    runs = []
    cur = [path[0]]
    for s in path[1:]:
        if s[0] != cur[-1][0]:
            runs.append(cur)
            cur = [s]
            continue
        if len(cur) >= 2:
            d0 = (cur[-1][1] - cur[-2][1], cur[-1][2] - cur[-2][2])
            d1 = (s[1] - cur[-1][1], s[2] - cur[-1][2])
            if d0 != d1:
                runs.append(cur)
                cur = [cur[-1]]
        cur.append(s)
    runs.append(cur)
    for r in runs:
        if len(r) < 2:
            continue
        a, b = r[0], r[-1]
        li = a[0]
        pa, pb = (gx(a[1]), gy(a[2])), (gx(b[1]), gy(b[2]))
        track([pa, pb], LAYERS[li], name, width)
        mark_seg(li, pa, pb, width / 2, code, RCLR + TRACK_W / 2)
        LANE_TARGETS.setdefault(code, []).append((li, pa, pb, width))

ROUTE_BOX = (gi(108.0), gi(150.0), gj(BY0), gj(TY1))

def route_net(name, width=TRACK_W, extra_groups=()):
    code = code_of(name)
    pads = PAD_TARGETS.get(code, [])
    # group pads: J1/J2 pads already joined by a fixed lane form one group
    groups = []
    lanes = [(li, a, b, w) for (li, a, b, w) in LANE_TARGETS.get(code, [])]
    lane_group = set()
    for li, a, b, w in lanes:
        lane_group |= lane_cells(li, a, b, w)
    joined = []
    for e in pads:
        ref = e[3]
        if lane_group and (ref.startswith("J1-") or ref.startswith("J2-")):
            joined.append(e)
            continue
        if ref.startswith("J1-") or ref.startswith("J2-"):
            # connector pads not on a lane: route to them (Q from J1-7, QX to J2-7)
            pass
        groups.append(pad_cells(e))
    if lane_group:
        for e in joined:
            lane_group |= pad_cells(e)
        groups.insert(0, lane_group)
    # prune cells that are not legally reachable
    groups = [{c for c in grp if grid[c[0]][c[2] * NX + c[1]] in (FREE, code)} for grp in groups]
    tree = groups.pop(0)
    while groups:
        # route the nearest remaining group to the tree
        groups.sort(key=lambda gset: min(abs(a[1] - b[1]) + abs(a[2] - b[2])
                                          for a in list(gset)[:20] for b in list(tree)[:400]))
        nxt = groups.pop(0)
        path = astar(code, nxt, tree, ROUTE_BOX)
        if path is None:
            FAILED.append(name)
            print("  FAILED", name, file=sys.stderr)
            tree |= nxt
            continue
        emit(code, path, width)
        tree |= nxt
        tree |= {(s[0], s[1], s[2]) for s in path}
    ROUTED.append(name)

ORDER = [("/E", TRACK_W), ("+5V", PWR_W), ("Q_COCO", TRACK_W), ("QX", TRACK_W), ("QX_INT", TRACK_W),
         ("E", TRACK_W), ("/Q", TRACK_W), ("CLRn", TRACK_W),
         ("T200", TRACK_W), ("OSC", TRACK_W), ("GND", PWR_W)]
# Order can be overridden by a previous attempt (see the retry below).
if os.environ.get("SSC_ORDER"):
    widths = dict(ORDER)
    ORDER = [(n, widths[n]) for n in os.environ["SSC_ORDER"].split(",")]
for n, w in ORDER:
    print("routing", n)
    route_net(n, w)
if FAILED:
    tries = int(os.environ.get("SSC_TRY", "0"))
    if tries < 8:
        names = [n for n, _ in ORDER]
        order = FAILED + [n for n in names if n not in FAILED]
        print("retrying with order", order)
        env = dict(os.environ, SSC_ORDER=",".join(order), SSC_TRY=str(tries + 1))
        sys.stdout.flush()
        os.execve(sys.executable, [sys.executable] + sys.argv, env)

# ---------------------------------------------------------------- GND pour
for L in LAYERS:
    z = P.ZONE(board)
    z.SetLayer(L)
    z.SetNet(net("GND"))
    z.SetMinThickness(mm(0.25))
    z.SetLocalClearance(mm(0.3))
    z.SetIslandRemovalMode(P.ISLAND_REMOVAL_MODE_ALWAYS)
    z.SetPadConnection(P.ZONE_CONNECTION_THERMAL)
    ol = z.Outline()
    ol.NewOutline()
    e = 0.6
    for x, y in [(BX0 + e, BY0 + e), (BX1 - e, BY0 + e), (BX1 - e, BY1 - e),
                 (BX0 + e, BY1 - e)]:
        ol.Append(mm(x), mm(y))
    board.Add(z)
P.ZONE_FILLER(board).Fill(board.Zones())

# ---------------------------------------------------------------- silkscreen
add_text(board, "SSC CLOCK FIXER rev A", 130.0, 117.0, size=1.2)
add_text(board, "CoCo / Multi-Pak side", 130.0, 154.0 - 0.0, size=0.9)
add_text(board, "SSC plugs in here", 130.0, 98.0 + 3.0, layer=P.F_Fab, size=0.9)
add_text(board, "1", colx(0) - 2.6, Y_ODD, size=0.8)
add_text(board, "1", colx(0), FING_TOP - 1.0, size=0.8)
add_text(board, "39", colx(19), FING_TOP - 1.0, size=0.8)
add_text(board, "2", colx(0), FING_TOP - 1.0, layer=P.B_SilkS, size=0.8)
add_text(board, "40", colx(19), FING_TOP - 1.0, layer=P.B_SilkS, size=0.8)
add_text(board, "Bevel finger edge 20-45 deg, hard gold", 130.0, TY1 + 2.0,
         layer=P.F_Fab, size=0.8)

# ---------------------------------------------------------------- project lib
# Save the two hand-made connector footprints into a project library so the
# board's footprints match a library (and can be reused or edited in KiCad).
LIBDIR = os.path.join(HERE, "ssc-fixer.pretty")
io = P.PCB_IO_KICAD_SEXPR()
if not os.path.isdir(LIBDIR):
    io.CreateLibrary(LIBDIR)
for fp in (J1, J2):
    lib_fp = P.FOOTPRINT(fp)
    lib_fp.SetPosition(V(0, 0))
    for pad in lib_fp.Pads():
        pad.SetNetCode(0)
    io.FootprintSave(LIBDIR, lib_fp)
with open(os.path.join(HERE, "fp-lib-table"), "w") as f:
    f.write('(fp_lib_table\n  (version 7)\n'
            '  (lib (name "ssc-fixer")(type "KiCad")(uri "${KIPRJMOD}/ssc-fixer.pretty")'
            '(options "")(descr "SSC fixer connectors"))\n)\n')

board.BuildConnectivity()
P.SaveBoard(OUT, board)
print("saved", OUT)
print("routed:", ROUTED)
print("failed:", FAILED)
