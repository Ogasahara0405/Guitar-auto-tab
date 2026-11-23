import sys, os, site
sys.path.append(site.getusersitepackages())
from PIL import Image
import numpy as np
BASE = r'C:/Users/iniad/Documents/個人開発/Guitar-auto-tab/_ref/tabframes'
for n in range(13, 31):
    A = np.asarray(Image.open(f'{BASE}/tf_{n:04d}.jpg').convert('RGB')).astype(int)
    H, W, _ = A.shape
    lum = A.mean(axis=2)
    # a vertical line: column where lum > 25 in >= 85% of rows y=25..155
    band = lum[25:156, :]
    cov = (band > 25).sum(axis=0) / band.shape[0]
    cols = [x for x in range(W) if cov[x] >= 0.85]
    groups = []
    for x in cols:
        if groups and x - groups[-1][1] <= 3:
            groups[-1][1] = x
        else:
            groups.append([x, x])
    info = []
    for g in groups:
        x0, x1 = g
        ymid = 90
        r, gg, b = A[ymid, (x0 + x1) // 2]
        r2, g2, b2 = A[150, (x0 + x1) // 2]
        r3, g3, b3 = A[35, (x0 + x1) // 2]
        info.append(f'[{x0}-{x1}] top(35)={r3},{g3},{b3} mid={r},{gg},{b} bot(150)={r2},{g2},{b2}')
    print(f'tf_{n:04d}: ' + ' ; '.join(info))
