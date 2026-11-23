import sys, os
from PIL import Image
import numpy as np

src_dir = r'C:/Users/iniad/Documents/個人開発/Guitar-auto-tab/_ref/tabframes'

def label_blobs(mask, min_area=25):
    h, w = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    blobs = []
    idx = np.argwhere(mask)
    for y0, x0 in idx:
        if visited[y0, x0]: continue
        stack = [(y0, x0)]
        visited[y0, x0] = True
        pts = []
        while stack:
            cy, cx = stack.pop()
            pts.append((cy, cx))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        stack.append((ny, nx))
        if len(pts) < min_area: continue
        ys = [p[0] for p in pts]; xs = [p[1] for p in pts]
        blobs.append([min(xs), max(xs), min(ys), max(ys), len(pts)])
    return blobs

for n in sys.argv[1:]:
    n = int(n)
    im = Image.open(os.path.join(src_dir, 'tf_%04d.jpg' % n)).convert('RGB')
    a = np.asarray(im).astype(int)
    h, w, _ = a.shape
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    lum = (r + g + b) / 3.0

    # --- horizontal string lines: rows with many mid-gray pixels ---
    grayish = (abs(r - g) < 30) & (abs(g - b) < 30) & (lum > 35) & (lum < 200)
    rowcount = grayish.sum(axis=1)
    thr = w * 0.45
    lines = [y for y in range(h) if rowcount[y] > thr]
    groups = []
    for y in lines:
        if groups and y - groups[-1][-1] <= 3:
            groups[-1].append(y)
        else:
            groups.append([y])
    line_ys = [sum(gp) / len(gp) for gp in groups]

    # --- orange cursor ---
    orange = (r > 100) & (r - b > 50) & (r - g > 25)
    ocount = orange.sum(axis=0)
    cursor_xs = [x for x in range(w) if ocount[x] > h * 0.25]

    # --- vertical barlines (thin, span most of staff) ---
    if line_ys:
        top, bot = line_ys[0] - 2, line_ys[-1] + 2
    else:
        top, bot = 50, 150
    band = (lum > 80)
    colcount = band[int(top):int(bot), :].sum(axis=0)
    bar_h = bot - top
    bar_xs = [x for x in range(w) if colcount[x] > bar_h * 0.8]
    bg = []
    for x in bar_xs:
        if bg and x - bg[-1][-1] <= 2:
            bg[-1].append(x)
        else:
            bg.append([x])
    bar_centers = [sum(gp) / len(gp) for gp in bg]

    # --- digits: bright pixels, minus pure-line pixels ---
    bright = lum > 80
    mask = bright.copy()
    # remove long horizontal runs (the string lines) row by row
    for y in range(h):
        xs = np.where(mask[y])[0]
        if len(xs) == 0: continue
        run = [xs[0]]
        for x in xs[1:]:
            if x - run[-1] <= 3:
                run.append(x)
            else:
                if len(run) > 60:
                    for xx in run: mask[y, xx] = False
                run = [x]
        if len(run) > 60:
            for xx in run: mask[y, xx] = False
    # also remove vertical barlines: long vertical runs
    for x in range(w):
        ys = np.where(mask[:, x])[0]
        if len(ys) == 0: continue
        run = [ys[0]]
        for y in ys[1:]:
            if y - run[-1] <= 3:
                run.append(y)
            else:
                if len(run) > 50:
                    for yy in run: mask[yy, x] = False
                run = [y]
        if len(run) > 50:
            for yy in run: mask[yy, x] = False

    blobs = label_blobs(mask, min_area=12)
    # merge blobs whose x-ranges overlap >50% and y-gap <= 10
    merged = True
    while merged:
        merged = False
        for i in range(len(blobs)):
            for j in range(i + 1, len(blobs)):
                A, B = blobs[i], blobs[j]
                ov = min(A[1], B[1]) - max(A[0], B[0])
                wA, wB = A[1] - A[0] + 1, B[1] - B[0] + 1
                gap = max(A[2], B[2]) - min(A[3], B[3])
                if ov > 0.4 * min(wA, wB) and gap <= 12:
                    blobs[i] = [min(A[0], B[0]), max(A[1], B[1]), min(A[2], B[2]), min(A[3], B[3]) if False else max(A[3], B[3]), A[4] + B[4]]
                    blobs.pop(j)
                    merged = True
                    break
            if merged: break
    blobs.sort(key=lambda t: t[0])

    print('=== frame', n, '===')
    print('line_ys:', ['%.1f' % v for v in line_ys])
    print('cursor_xs:', cursor_xs, '(count %d)' % len(cursor_xs))
    print('bar_xs:', ['%.0f' % v for v in bar_centers])
    print('digit blobs:')
    for bl in blobs:
        cx = (bl[0] + bl[1]) / 2; cy = (bl[2] + bl[3]) / 2
        if line_ys:
            dists = [abs(v - cy) for v in line_ys]
            nearest = int(np.argmin(dists)) + 1
            d = dists[nearest - 1]
        else:
            nearest, d = -1, 999
        print('  x=%d-%d cx=%.0f y=%d-%d cy=%.0f area=%d -> line %d (d=%.1f)' % (bl[0], bl[1], cx, bl[2], bl[3], cy, bl[4], nearest, d))
    print()
