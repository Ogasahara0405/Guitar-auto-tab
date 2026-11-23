import sys, os, site
sys.path.append(site.getusersitepackages())
from PIL import Image
import numpy as np

src = sys.argv[1]
outdir = sys.argv[2] if len(sys.argv) > 2 else None
frame = os.path.basename(src).split('.')[0]

a = np.asarray(Image.open(src).convert('L')).astype(float)
H, W = a.shape

# ---- staff lines ----
counts = ((a > 42) & (a < 215)).sum(axis=1)
peaks = []
y = 60
while y < 155:
    if counts[y] > 250:
        y0 = y
        while y < 155 and counts[y] > 120:
            y += 1
        peaks.append((y0 + y - 1) / 2)
    y += 1
# merge peaks closer than 6px
staff = []
for p in peaks:
    if staff and p - staff[-1] < 6:
        staff[-1] = (staff[-1] + p) / 2
    else:
        staff.append(p)
print('STAFF', [round(s, 1) for s in staff])

# ---- cursor (color) ----
imc = np.asarray(Image.open(src).convert('RGB')).astype(int)
warm = ((imc[:, :, 0] > imc[:, :, 2] + 6) & ((imc.sum(axis=2) / 3) > 35)).sum(axis=0)
cand = [x for x in range(W) if warm[x] >= 25]
# group contiguous
cur_groups = []
for x in cand:
    if cur_groups and x - cur_groups[-1][1] <= 3:
        cur_groups[-1][1] = x
    else:
        cur_groups.append([x, x])
print('CURSOR', cur_groups)

# ---- digit mask via horizontal background subtraction ----
k = 21
pad = np.pad(a, ((0, 0), (k, k)), mode='edge')
cs = np.cumsum(pad, axis=1)
cs = np.concatenate([np.zeros((H, 1)), cs], axis=1)
win = cs[:, 2*k+1:] - cs[:, :-(2*k+1)]   # sum over window of 2k+1? adjust
# simpler: uniform_filter1d via cumsum
bg = np.zeros_like(a)
half = k
for x in range(W):
    lo = max(0, x - half); hi = min(W, x + half + 1)
    bg[:, x] = a[:, lo:hi].mean(axis=1)
diff = a - bg
mask = diff > 18
mask[:58, :] = False
mask[152:, :] = False

# dilate: 2 horizontal, 1 vertical
d = mask.copy()
d[:, 1:] |= mask[:, :-1]; d[:, :-1] |= mask[:, 1:]
d[1:, :] |= d[:-1, :]; d[:-1, :] |= d[1:, :]
d[:, 1:] |= d[:, :-1]; d[:, :-1] |= d[:, 1:]
mask = d

lab = np.zeros((H, W), dtype=bool)
comps = []
for yy in range(58, 152):
    for xx in range(W):
        if mask[yy, xx] and not lab[yy, xx]:
            stack = [(yy, xx)]
            lab[yy, xx] = True
            x0 = x1 = xx; y0 = y1 = yy; n = 0
            while stack:
                cy, cx = stack.pop()
                n += 1
                x0 = min(x0, cx); x1 = max(x1, cx); y0 = min(y0, cy); y1 = max(y1, cy)
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = cy + dy, cx + dx
                    if 58 <= ny < 152 and 0 <= nx < W and mask[ny, nx] and not lab[ny, nx]:
                        lab[ny, nx] = True
                        stack.append((ny, nx))
            w = x1 - x0 + 1; h = y1 - y0 + 1
            if n >= 12 and 2 <= w <= 30 and 4 <= h <= 30:
                comps.append(dict(x0=x0, x1=x1, y0=y0, y1=y1, n=n))
comps.sort(key=lambda c: (c['x0'], c['y0']))

def nearest(yc):
    dists = [abs(yc - s) for s in staff]
    i = dists.index(min(dists))
    return i + 1, min(dists)

print('BLOBS:')
for c in comps:
    yc = (c['y0'] + c['y1']) / 2
    s, dd = nearest(yc)
    c['yc'] = yc; c['string'] = s
    print(f"  x {c['x0']:4d}-{c['x1']:4d}  y {c['y0']:3d}-{c['y1']:3d}  yc {yc:5.1f}  string~{s} d={dd:.1f}")

events = []
for c in comps:
    if events and c['x0'] - events[-1]['x1'] <= 12 and abs(c['yc'] - events[-1]['ycs'][0]) < 1000:
        ev = events[-1]
        ev['x1'] = max(ev['x1'], c['x1'])
        ev['blobs'].append(c)
        ev['ycs'].append(c['yc'])
    else:
        events.append(dict(x0=c['x0'], x1=c['x1'], blobs=[c], ycs=[c['yc']]))
print('EVENTS:')
for i, ev in enumerate(events):
    x = (ev['x0'] + ev['x1']) / 2
    notes = [(b['string'], b['yc']) for b in ev['blobs']]
    print(f"  ev{i:02d} x~{x:.0f}  {notes}")

if outdir:
    os.makedirs(outdir, exist_ok=True)
    imr = Image.open(src).convert('RGB')
    for i, ev in enumerate(events):
        cx0 = max(0, ev['x0'] - 14); cx1 = min(W, ev['x1'] + 14)
        crop = imr.crop((cx0, 58, cx1, 152))
        w, h = crop.size
        scale = max(1, min(14, 1120 // max(w, 1)))
        crop.resize((w * scale, h * scale), Image.LANCZOS).save(
            os.path.join(outdir, f'{frame}_ev{i:02d}_x{int((ev["x0"]+ev["x1"])//2)}.png'))
    print('CROPS_SAVED', outdir)
