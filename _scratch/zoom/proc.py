import sys, os, site, json, re
sys.path.append(site.getusersitepackages())
from PIL import Image
import numpy as np

STAFF = [69.5, 84.0, 98.5, 112.5, 127.0, 142.0]  # y of lines: string 1..6

def process(src, outdir, frame):
    a = np.asarray(Image.open(src).convert('L')).astype(float)
    H, W = a.shape
    imc = np.asarray(Image.open(src).convert('RGB')).astype(int)
    warm = ((imc[:, :, 0] > imc[:, :, 2] + 6) & ((imc.sum(axis=2) / 3) > 35)).sum(axis=0)
    cand = [x for x in range(W) if warm[x] >= 25]
    cur_groups = []
    for x in cand:
        if cur_groups and x - cur_groups[-1][1] <= 3:
            cur_groups[-1][1] = x
        else:
            cur_groups.append([x, x])

    half = 21
    bg = np.zeros_like(a)
    for x in range(W):
        lo = max(0, x - half); hi = min(W, x + half + 1)
        bg[:, x] = a[:, lo:hi].mean(axis=1)
    diff = a - bg
    mask = diff > 18
    mask[:61, :] = False
    mask[152:, :] = False
    # dilate 2x horizontal, 1x vertical
    d = mask.copy()
    d[:, 1:] |= mask[:, :-1]; d[:, :-1] |= mask[:, 1:]
    d[1:, :] |= d[:-1, :]; d[:-1, :] |= d[1:, :]
    d[:, 1:] |= d[:, :-1]; d[:, :-1] |= d[:, 1:]
    mask = d

    lab = np.zeros((H, W), dtype=bool)
    comps = []
    for yy in range(61, 152):
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
                        if 61 <= ny < 152 and 0 <= nx < W and mask[ny, nx] and not lab[ny, nx]:
                            lab[ny, nx] = True
                            stack.append((ny, nx))
                w = x1 - x0 + 1; h = y1 - y0 + 1
                if n >= 25 and w <= 45 and h <= 48 and h >= 7 and w >= 3:
                    comps.append(dict(x0=x0, x1=x1, y0=y0, y1=y1, n=n))

    # merge components with x overlap and y gap <= 2
    merged = True
    while merged:
        merged = False
        for i in range(len(comps)):
            for j in range(i + 1, len(comps)):
                A, B = comps[i], comps[j]
                ov = min(A['x1'], B['x1']) - max(A['x0'], B['x0'])
                gap = max(0, max(A['y0'], B['y0']) - min(A['y1'], B['y1']))
                if ov >= 2 and gap <= 2:
                    A['x0'] = min(A['x0'], B['x0']); A['x1'] = max(A['x1'], B['x1'])
                    A['y0'] = min(A['y0'], B['y0']); A['y1'] = max(A['y1'], B['y1'])
                    A['n'] += B['n']
                    comps.pop(j)
                    merged = True
                    break
            if merged: break

    comps.sort(key=lambda c: (c['x0'] + c['x1']) / 2)

    events = []
    for c in comps:
        yc = (c['y0'] + c['y1']) / 2
        strings = [i + 1 for i, s in enumerate(STAFF) if c['y0'] + 2 <= s <= c['y1'] - 2]
        if not strings:
            dd = [abs(yc - s) for s in STAFF]
            strings = [dd.index(min(dd)) + 1]
        c['yc'] = yc
        c['strings'] = strings
        c['cx'] = (c['x0'] + c['x1']) / 2
        events.append(c)

    # group events with x gap <= 12 into one cluster? keep separate but report clusters
    clusters = []
    for c in events:
        if clusters and c['x0'] - clusters[-1]['x1'] <= 12:
            cl = clusters[-1]
            cl['x1'] = max(cl['x1'], c['x1'])
            cl['comps'].append(c)
        else:
            clusters.append(dict(x0=c['x0'], x1=c['x1'], comps=[c]))

    print(f'== {frame} ==')
    print('CURSOR', cur_groups)
    for c in events:
        print(f"  x {c['x0']:4d}-{c['x1']:4d} cx {c['cx']:6.1f} y {c['y0']:3d}-{c['y1']:3d} strings {c['strings']}")
    print('CLUSTERS:')
    for cl in clusters:
        cx = (cl['x0'] + cl['x1']) / 2
        notes = [(b['strings'], round(b['cx'])) for b in cl['comps']]
        print(f"  cx {cx:6.1f}  {notes}")

    if outdir:
        os.makedirs(outdir, exist_ok=True)
        imr = Image.open(src).convert('RGB')
        # half crops at 2.4x
        for hi, (hx0, hx1) in enumerate([(0, 640), (640, 1280)]):
            crop = imr.crop((hx0, 30, hx1, 160))
            w, h = crop.size
            crop.resize((int(w * 2.4), int(h * 2.4)), Image.LANCZOS).save(
                os.path.join(outdir, f'{frame}_half{hi}.png'))
        # event crops at 8-12x
        for i, cl in enumerate(clusters):
            cx0 = max(0, cl['x0'] - 14); cx1 = min(W, cl['x1'] + 14)
            crop = imr.crop((cx0, 58, cx1, 152))
            w, h = crop.size
            scale = max(1, min(12, 1100 // max(w, 1)))
            crop.resize((w * scale, h * scale), Image.LANCZOS).save(
                os.path.join(outdir, f'{frame}_ev{i:02d}_x{int((cl["x0"]+cl["x1"])//2)}.png'))
    return events, clusters, cur_groups

if __name__ == '__main__':
    frames = sys.argv[1:]
    for src in frames:
        frame = os.path.splitext(os.path.basename(src))[0]
        outdir = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), 'crops', frame)
        process(src, outdir, frame)
