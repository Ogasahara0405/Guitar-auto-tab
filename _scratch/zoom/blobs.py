import sys, os, site
sys.path.append(site.getusersitepackages())
from PIL import Image
import numpy as np

src = sys.argv[1]
im = Image.open(src).convert('L')
a = np.asarray(im).astype(int)
H, W = a.shape

# detect staff line rows: rows where many pixels are mid-gray (line color ~ lum 60-200)
line_rows = []
for y in range(H):
    row = a[y]
    c = int(((row > 45) & (row < 210)).sum())
    line_rows.append(c)
# find peaks (local maxima above 400)
staff = []
y = 30
while y < 155:
    if line_rows[y] > 350:
        y0 = y
        while y < 155 and line_rows[y] > 200:
            y += 1
        staff.append((y0 + y - 1) // 2)
    y += 1
print('STAFF_LINES', staff)

# warm cursor detection (color image)
imc = Image.open(src).convert('RGB')
ac = np.asarray(imc).astype(int)
warm = ((ac[:, :, 0] > ac[:, :, 2] + 6) & ((ac.sum(axis=2) / 3) > 35)).sum(axis=0)
cand = [x for x in range(W) if warm[x] >= 25]
print('CURSOR_COLS', cand)

# digit blobs: bright pixels in staff region
mask = (a > 120)
mask[:55, :] = False   # exclude P.M. text row area
mask[150:, :] = False
# remove staff lines themselves: for each staff line row, clear only if row is "line-like" over most of width? No - digits overlap lines. Instead dilate later.
# connected components (4-conn) via simple stack
lab = np.zeros((H, W), dtype=int)
cur = 0
comps = []
for yy in range(55, 150):
    for xx in range(W):
        if mask[yy, xx] and lab[yy, xx] == 0:
            cur += 1
            stack = [(yy, xx)]
            lab[yy, xx] = cur
            pts = []
            while stack:
                cy, cx = stack.pop()
                pts.append((cy, cx))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = cy + dy, cx + dx
                    if 55 <= ny < 150 and 0 <= nx < W and mask[ny, nx] and lab[ny, nx] == 0:
                        lab[ny, nx] = cur
                        stack.append((ny, nx))
            ys = [p[0] for p in pts]
            xs = [p[1] for p in pts]
            if len(pts) >= 12 and (max(xs) - min(xs)) >= 2 and (max(ys) - min(ys)) >= 3:
                comps.append((min(xs), max(xs), min(ys), max(ys), len(pts)))
comps.sort()
print('BLOBS x0 x1 y0 y1 npx  | nearest-line guess')
for x0, x1, y0, y1, n in comps:
    yc = (y0 + y1) / 2
    if staff:
        dists = [abs(yc - s) for s in staff]
        si = dists.index(min(dists))
        sstr = f'string~{si+1} (line y={staff[si]}, yc={yc:.1f}, d={min(dists):.1f})'
    else:
        sstr = f'yc={yc:.1f}'
    print(f'{x0:4d} {x1:4d} {y0:4d} {y1:4d} {n:5d}  | {sstr}')
