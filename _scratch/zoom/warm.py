import sys, os, site
sys.path.append(site.getusersitepackages())
from PIL import Image
src = sys.argv[1]
im = Image.open(src).convert('RGB')
W,H = im.size
px = im.load()
print('== warm columns (r>b+6, lum>35) ==')
for x in range(W):
    ys = []
    for y in range(25, 155):
        r,g,b = px[x,y]
        if r > b+6 and (r+g+b)/3 > 35:
            ys.append(y)
    if len(ys) >= 25:
        # sample color
        yy = ys[len(ys)//2]
        print('x', x, 'n', len(ys), 'ytop', ys[0], 'ybot', ys[-1], 'color', px[x,yy])
