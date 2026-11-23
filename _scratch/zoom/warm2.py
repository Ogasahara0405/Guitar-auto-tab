import sys, os, site
sys.path.append(site.getusersitepackages())
from PIL import Image
import numpy as np
src = sys.argv[1]
imc = np.asarray(Image.open(src).convert('RGB')).astype(int)
H, W, _ = imc.shape
r, g, b = imc[:,:,0], imc[:,:,1], imc[:,:,2]
lum = imc.sum(axis=2)/3
# warm anywhere in staff rows 60..150
warmmask = (r > b + 4) & (lum > 28)
sub = warmmask[60:150, :]
cnt = sub.sum(axis=0)
cand = [(x, int(cnt[x])) for x in range(W) if cnt[x] >= 20]
print('warm cols (>=20 rows):', cand)
# also non-neutral vertical lines (any color, full height) with lum>28
vert = (np.abs(r-b) > 4) & (lum > 28)
cnt2 = vert[60:150, :].sum(axis=0)
cand2 = [(x, int(cnt2[x])) for x in range(W) if cnt2[x] >= 40]
print('colored vertical cols (>=40 rows):', cand2)
