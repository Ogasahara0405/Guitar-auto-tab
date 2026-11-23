import sys, os, site
sys.path.append(site.getusersitepackages())
from PIL import Image
src = sys.argv[1]
im = Image.open(src).convert('RGB')
W,H = im.size
px = im.load()
# find horizontal staff lines: rows with many bright-ish gray pixels
rows = []
for y in range(H):
    c = 0
    for x in range(0, W, 4):
        r,g,b = px[x,y]
        if r>90 and g>90 and b>90 and abs(r-g)<40 and abs(g-b)<40:
            c += 1
    rows.append(c)
print('W,H', W, H)
# report candidate line rows
import statistics
thr = max(rows)/3
lines = []
y = 0
while y < H:
    if rows[y] > thr:
        y0 = y
        while y < H and rows[y] > thr:
            y += 1
        lines.append((y0+y-1)//2)
    y += 1
print('staff line rows:', lines)
# find colored vertical cursor: columns with saturated warm color (r>>b)
best = []
for x in range(W):
    c = 0
    for y in range(H):
        r,g,b = px[x,y]
        if r>70 and r-b>30 and r>=g:
            c += 1
    best.append(c)
mx = max(best)
print('max warm col count', mx)
cand = [(x,best[x]) for x in range(W) if best[x] > mx*0.4 and best[x] > H*0.15]
print('warm columns:', cand)
# sample colors at those columns mid-height
for x,_ in cand[:20]:
    ys = [y for y in range(H) if (lambda t: t[0]>70 and t[0]-t[2]>30 and t[0]>=t[1])(px[x,y])]
    if ys:
        yy = ys[len(ys)//2]
        print('col', x, 'n', len(ys), 'color', px[x,yy])
