import sys, os, site
sys.path.append(site.getusersitepackages())
from PIL import Image
import numpy as np

STAFF = [69.5, 84.0, 98.5, 112.5, 127.0, 142.0]

def run(src):
    frame = os.path.splitext(os.path.basename(src))[0]
    a = np.asarray(Image.open(src).convert('L')).astype(float)
    H, W = a.shape
    imc = np.asarray(Image.open(src).convert('RGB')).astype(int)
    warm = ((imc[:, :, 0] > imc[:, :, 2] + 6) & ((imc.sum(axis=2) / 3) > 28)).sum(axis=0)
    cand = [x for x in range(W) if warm[x] >= 18]
    cur = []
    for x in cand:
        if cur and x - cur[-1][1] <= 3:
            cur[-1][1] = x
        else:
            cur.append([x, x])

    half = 21
    bg = np.zeros_like(a)
    for x in range(W):
        lo = max(0, x - half); hi = min(W, x + half + 1)
        bg[:, x] = a[:, lo:hi].mean(axis=1)
    diff = a - bg
    mask = diff > 18
    mask[:58, :] = False
    mask[152:, :] = False
    # column groups: any column with mask pixels in digit rows 62..150
    colhas = mask.any(axis=0)
    # clean: require runs
    groups = []
    x = 0
    while x < W:
        if colhas[x]:
            x0 = x
            while x < W and colhas[x]:
                x += 1
            # gap-merge with previous if gap <= 5
            if groups and x0 - groups[-1][1] <= 5:
                groups[-1][1] = x - 1
            else:
                groups.append([x0, x - 1])
        else:
            x += 1

    print(f'== {frame} ==')
    print('CURSOR_WARM', cur)
    notes_all = []
    for x0, x1 in groups:
        if x1 - x0 > 40:  # barline or cursor column run
            # check: thin vertical line? skip if width<=8 and tall
            pass
        strings = []
        for i, s in enumerate(STAFF):
            ys0, ys1 = int(s - 7), int(s + 7)
            box = mask[ys0:ys1 + 1, x0:x1 + 1]
            if box.sum() >= 10:
                strings.append(i + 1)
        # skip pure vertical lines (barline/cursor): mask column continuous over 60+ rows with width<=8
        colsum = mask[:, x0:x1 + 1].sum()
        w = x1 - x0 + 1
        vert = (w <= 8 and colsum > 60)
        if vert:
            print(f'  [skip vertical] x {x0}-{x1}')
            continue
        cx = (x0 + x1) / 2
        print(f'  x {x0:4d}-{x1:4d} cx {cx:6.1f} strings {strings}')
        notes_all.append((x0, x1, cx, strings))
    return notes_all, cur

for src in sys.argv[1:]:
    run(src)
