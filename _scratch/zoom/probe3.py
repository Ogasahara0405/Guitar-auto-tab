import sys, os, site
sys.path.append(site.getusersitepackages())
from PIL import Image
import numpy as np
src, x0, x1 = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
A = np.asarray(Image.open(src).convert('RGB')).astype(int)
for y in [30, 45, 65, 80, 95, 110, 125, 140, 150]:
    row = []
    for x in range(x0, x1):
        r, g, b = A[y, x]
        row.append(f'{x}:{r:3d},{g:3d},{b:3d}')
    print(f'y={y:3d} ' + ' | '.join(row))
