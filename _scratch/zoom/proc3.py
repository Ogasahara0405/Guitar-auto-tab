import sys, os, site
sys.path.append(site.getusersitepackages())
from PIL import Image
import numpy as np

STAFF = [69.5, 84.0, 98.5, 112.5, 127.0, 142.0]
BASE = r'C:/Users/iniad/Documents/個人開発/Guitar-auto-tab/_ref/tabframes'

def load(n):
    return np.asarray(Image.open(f'{BASE}/tf_{n:04d}.jpg').convert('RGB')).astype(int)

def diff_groups(A, B, thr=40, minrows=25):
    d = np.abs(A - B).sum(axis=2)
    cnt = (d > thr).sum(axis=0)
    groups = []
    for x in range(A.shape[1]):
        if cnt[x] >= minrows:
            if groups and x - groups[-1][1] <= 5:
                groups[-1][1] = x
            else:
                groups.append([x, x])
    return groups

def warm_cols(A, minrows=18):
    warm = ((A[:, :, 0] > A[:, :, 2] + 6) & ((A.sum(axis=2) / 3) > 28)).sum(axis=0)
    groups = []
    for x in range(A.shape[1]):
        if warm[x] >= minrows:
            if groups and x - groups[-1][1] <= 3:
                groups[-1][1] = x
            else:
                groups.append([x, x])
    return groups

def notes_of(src):
    frame = os.path.splitext(os.path.basename(src))[0]
    n = int(frame.split('_')[1])
    imc = load(n)
    a = imc.mean(axis=2)
    H, W = a.shape
    half = 21
    bg = np.zeros_like(a)
    for x in range(W):
        lo = max(0, x - half); hi = min(W, x + half + 1)
        bg[:, x] = a[:, lo:hi].mean(axis=1)
    diff = a - bg
    mask = diff > 16
    mask[:60, :] = False
    mask[151:, :] = False

    colhas = mask.any(axis=0)
    groups = []
    x = 0
    while x < W:
        if colhas[x]:
            x0 = x
            while x < W and colhas[x]:
                x += 1
            if groups and x0 - groups[-1][1] <= 4:
                groups[-1][1] = x - 1
            else:
                groups.append([x0, x - 1])
        else:
            x += 1

    events = []
    for x0, x1 in groups:
        rows_cov = int(mask[60:151, x0:x1 + 1].any(axis=1).sum())
        w = x1 - x0 + 1
        if w <= 10 and rows_cov >= 80:
            continue  # barline or cursor
        strings = []
        for i, s in enumerate(STAFF):
            y0, y1 = int(s - 7), int(s + 7)
            if mask[y0:y1 + 1, x0:x1 + 1].sum() >= 8:
                strings.append(i + 1)
        cols = np.where(mask[:, x0:x1 + 1].any(axis=0))[0] + x0
        cx = float(np.median(cols))
        events.append((x0, x1, cx, strings))

    # merge events with close cx (split fragments)
    merged = []
    for ev in events:
        if merged and ev[2] - merged[-1][2] <= 12 and set(ev[3]) == set(merged[-1][3]):
            m = merged[-1]
            merged[-1] = (min(m[0], ev[0]), max(m[1], ev[1]), (m[2] + ev[2]) / 2, m[3])
        else:
            merged.append(ev)

    # cursor: warm in frame + intersection of diff groups with neighbors
    g_prev = diff_groups(load(n - 1), imc) if n > 1 else []
    g_next = diff_groups(imc, load(n + 1)) if n < 126 else []
    inter = []
    for p in g_prev:
        for q in g_next:
            if not (p[1] < q[0] - 4 or q[1] < p[0] - 4):
                inter.append([min(p[0], q[0]), max(p[1], q[1])])
    wc = warm_cols(imc)
    cur = []
    for g in inter + wc:
        if not any(not (g[1] < c[0] - 4 or c[1] < g[0] - 4) for c in cur):
            cur.append(g)

    print(f'== {frame} ==')
    print('CURSOR', cur)
    for x0, x1, cx, strings in merged:
        print(f'  cx {cx:7.1f}  x {x0:4d}-{x1:4d}  strings {strings}')
    return merged, cur

if __name__ == '__main__':
    for src in sys.argv[1:]:
        notes_of(src)
