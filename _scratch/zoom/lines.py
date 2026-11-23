import sys, os, site
sys.path.append(site.getusersitepackages())
from PIL import Image
src = sys.argv[1]
im = Image.open(src).convert('RGB')
W,H = im.size
px = im.load()
counts = []
for y in range(H):
    c = 0
    for x in range(0, W):
        r,g,b = px[x,y]
        lum = (r+g+b)/3
        if lum > 42 and abs(r-b) < 25 and abs(r-g) < 25:
            c += 1
    counts.append(c)
for y in range(H):
    bar = '#' * (counts[y]//20)
    print(f'{y:3d} {counts[y]:4d} {bar}')
