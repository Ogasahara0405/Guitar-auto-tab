import sys, os, site
sys.path.append(site.getusersitepackages())
from PIL import Image
import numpy as np
src = sys.argv[1]
a = np.asarray(Image.open(src).convert('L')).astype(float)
H, W = a.shape
half = 21
bg = np.zeros_like(a)
for x in range(W):
    lo = max(0, x - half); hi = min(W, x + half + 1)
    bg[:, x] = a[:, lo:hi].mean(axis=1)
diff = a - bg
for y in range(100, 152, 2):
    row = ''
    for x in range(100, 200):
        v = diff[y, x]
        row += '#' if v > 18 else ('.' if v > 8 else ' ')
    print(f'{y:3d} {row}')
