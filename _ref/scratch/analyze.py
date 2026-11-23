import sys, os
from PIL import Image
import numpy as np

src_dir = r'C:/Users/iniad/Documents/個人開発/Guitar-auto-tab/_ref/tabframes'

for n in sys.argv[1:]:
    n = int(n)
    im = Image.open(os.path.join(src_dir, 'tf_%04d.jpg' % n)).convert('RGB')
    a = np.asarray(im).astype(int)
    h, w, _ = a.shape
    r, g, b = a[:,:,0], a[:,:,1], a[:,:,2]
    lum = (r + g + b) / 3.0

    # horizontal string lines: rows where many pixels are moderately bright and gray
    gray = (abs(r-g) < 25) & (abs(g-b) < 25) & (lum > 60)
    rowcount = gray.sum(axis=1)
    lines = []
    for y in range(h):
        if rowcount[y] > w * 0.5:
            lines.append(y)
    # group consecutive
    groups = []
    for y in lines:
        if groups and y - groups[-1][-1] <= 2:
            groups[-1].append(y)
        else:
            groups.append([y])
    line_ys = [sum(gp)/len(gp) for gp in groups]

    # orange cursor: high r, mid g, low b, distinctly orange
    orange = (r > 120) & (r - b > 60) & (g > 60) & (g < r - 30)
    ocount = orange.sum(axis=0)
    cursor_xs = [x for x in range(w) if ocount[x] > h * 0.3]

    # digit blobs: bright-ish pixels (lum>90), not part of long horizontal lines
    bright = lum > 95
    # remove line rows (within 2px of a line y) only where the whole row is line-like? No:
    # digits overlap lines. Instead remove pixels belonging to runs > 100px horizontally.
    mask = bright.copy()
    for y in range(h):
        xs = np.where(mask[y])[0]
        if len(xs) == 0: continue
        # find runs
        run = [xs[0]]
        for x in xs[1:]:
            if x - run[-1] <= 2:
                run.append(x)
            else:
                if len(run) > 100:
                    for xx in run: mask[y, xx] = False
                run = [x]
        if len(run) > 100:
            for xx in run: mask[y, xx] = False

    # connected components (simple flood via scipy if available, else manual labeling)
    try:
        from scipy import ndimage
        lbl, num = ndimage.label(mask, structure=np.ones((3,3)))
        blobs = []
        for i in range(1, num+1):
            ys, xs = np.where(lbl == i)
            if len(ys) < 30: continue
            blobs.append((xs.min(), xs.max(), ys.min(), ys.max(), len(ys)))
    except ImportError:
        # simple BFS labeling
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
                for dy in (-1,0,1):
                    for dx in (-1,0,1):
                        ny, nx = cy+dy, cx+dx
                        if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not visited[ny, nx]:
                            visited[ny, nx] = True
                            stack.append((ny, nx))
            if len(pts) < 30: continue
            ys = [p[0] for p in pts]; xs = [p[1] for p in pts]
            blobs.append((min(xs), max(xs), min(ys), max(ys), len(pts)))
    blobs.sort(key=lambda t: t[0])

    print('frame', n)
    print('lines:', ['%.1f' % v for v in line_ys])
    print('cursor xs:', cursor_xs[:5], '...' if len(cursor_xs) > 5 else '', 'count', len(cursor_xs))
    print('blobs (x0,x1,y0,y1,area):')
    for bl in blobs:
        cx = (bl[0]+bl[1])/2; cy = (bl[2]+bl[3])/2
        # nearest line
        nearest = min(range(len(line_ys)), key=lambda i: abs(line_ys[i]-cy)) if line_ys else -1
        print('  x=%d-%d cx=%.0f y=%d-%d cy=%.0f area=%d near_line=%d' % (bl[0], bl[1], cx, bl[2], bl[3], cy, bl[4], nearest+1))
    print()
