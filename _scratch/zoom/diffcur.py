import sys, os, site
sys.path.append(site.getusersitepackages())
from PIL import Image
import numpy as np
a = np.asarray(Image.open(sys.argv[1]).convert('RGB')).astype(int)
b = np.asarray(Image.open(sys.argv[2]).convert('RGB')).astype(int)
d = np.abs(a - b).sum(axis=2)
cnt = (d > 40).sum(axis=0)
cand = [(x, int(cnt[x])) for x in range(a.shape[1]) if cnt[x] >= 30]
print('diff columns (>=30 rows):', cand)
# group
groups = []
for x, c in cand:
    if groups and x - groups[-1][1] <= 6:
        groups[-1][1] = x; groups[-1][2] = max(groups[-1][2], c)
    else:
        groups.append([x, x, c])
print('groups [x0,x1,maxrows]:', groups)
