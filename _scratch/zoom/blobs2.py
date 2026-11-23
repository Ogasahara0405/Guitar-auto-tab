import sys, os, site
sys.path.append(site.getusersitepackages())
from PIL import Image
import numpy as np

src = sys.argv[1]
outdir = sys.argv[2] if len(sys.argv) > 2 else None
frame = os.path.basename(src).split('.')[0]

im = Image.open(src).convert('L')
a = np.asarray(im).astype(int)
H, W = a.shape

# ---- staff lines ----
counts = ((a > 42) & (a < 215)).sum(axis=1)
peaks = []
for y in range(55, 155):
    if counts[y] > 300:
        y0 = y
        while y < 155 and counts[y] > 150:
            y += 1
        peaks.append(((y0 + y - 1) / 2, max(counts[y0:y])))
staff = [p[0] for p in peaks]
print('STAFF_CANDIDATES', [(round(p[0], 1), p[1]) for p in peaks])

# ---- cursor (color) ----
imc = np.asarray(Image.open(src).convert('RGB')).astype(int)
warm = ((imc[:, :, 0] > imc[:, :, 2] + 6) & ((imc.sum(axis=2) / 3) > 35)).sum(axis=0)
cand = [x for x in range(W) if warm[x] >= 25]
print('CURSOR_COLS', cand)

# ---- digit edges ----
gx = np.zeros_like(a); gy = np.zeros_like(a)
gx[:, 1:-1] = np.abs(a[:, 2:] - a[:, :-2])
gy[1:-1, :] = np.abs(a[2:, :] - a[:-2, :])
grad = np.maximum(gx, gy)
mask = grad > 22
mask[:58, :] = False
mask[152:, :] = False

# dilate 2x to connect strokes
for _ in range(2):
    d = mask.copy()
    d[1:, :] |= mask[:-1, :]
    d[:-1, :] |= mask[1:, :]
    d[:, 1:] |= mask[:, :-1]
    d[:, :-1] |= mask[:, 1:]
    mask = d

lab = np.zeros((H, W), dtype=int)
comps = []
cur = 0
for yy in range(58, 152):
    for xx in range(W):
        if mask[yy, xx] and lab[yy, xx] == 0:
            cur += 1
            stack = [(yy, xx)]
            lab[yy, xx] = cur
            x0 = x1 = xx; y0 = y1 = yy; n = 0
            while stack:
                cy, cx = stack.pop()
                n += 1
                x0 = min(x0, cx); x1 = max(x1, cx); y0 = min(y0, cy); y1 = max(y1, cy)
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = cy + dy, cx + dx
                    if 58 <= ny < 152 and 0 <= nx < W and mask[ny, nx] and lab[ny, nx] == 0:
                        lab[ny, nx] = cur
                        stack.append((ny, nx))
            w = x1 - x0 + 1; h = y1 - y0 + 1
            if n >= 18 and w >= 3 and h >= 4 and not (h > 45 and w < 12):
                comps.append(dict(x0=x0, x1=x1, y0=y0, y1=y1, n=n))
comps.sort(key=lambda c: c['x0'])

# assign strings by y center of the *bright core*: use y center of comp
def nearest(yc):
    if not staff: return None
    dists = [abs(yc - s) for s in staff]
    i = dists.index(min(dists))
    return i + 1, staff[i], min(dists)

print('BLOBS:')
for c in comps:
    yc = (c['y0'] + c['y1']) / 2
    s = nearest(yc)
    c['yc'] = yc
    c['string'] = s[0] if s else None
    print(f"  x {c['x0']:4d}-{c['x1']:4d}  y {c['y0']:3d}-{c['y1']:3d}  yc {yc:5.1f}  string~{c['string']}  d={s[2]:.1f}" if s else str(c))

# group into events (x gap <= 10)
events = []
for c in comps:
    if events and c['x0'] - events[-1]['x1'] <= 10:
        ev = events[-1]
        ev['x1'] = max(ev['x1'], c['x1'])
        ev['blobs'].append(c)
    else:
        events.append(dict(x0=c['x0'], x1=c['x1'], blobs=[c]))
print('EVENTS:')
for i, ev in enumerate(events):
    x = (ev['x0'] + ev['x1']) / 2
    notes = [(b['string'], (b['y0'] + b['y1']) / 2) for b in ev['blobs']]
    print(f"  x~{x:.0f}  blobs: {notes}")

# zoom crops per event
if outdir:
    os.makedirs(outdir, exist_ok=True)
    for i, ev in enumerate(events):
        cx0 = max(0, ev['x0'] - 12); cx1 = min(W, ev['x1'] + 12)
        cy0, cy1 = 58, 152
        crop = Image.open(src).convert('RGB').crop((cx0, cy0, cx1, cy1))
        w, h = crop.size
        scale = max(1, min(12, 1100 // max(w, 1)))
        crop = crop.resize((w * scale, h * scale), Image.LANCZOS)
        out = os.path.join(outdir, f'{frame}_ev{i:02d}_x{int((ev["x0"]+ev["x1"])//2)}.png')
        crop.save(out)
    print('CROPS_SAVED', outdir)
