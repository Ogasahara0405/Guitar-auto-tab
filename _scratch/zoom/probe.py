import sys, os, site
sys.path.append(site.getusersitepackages())
from PIL import Image
src = sys.argv[1]
im = Image.open(src).convert('RGB')
W,H = im.size
px = im.load()
# background sample
print('corner', px[2,2], 'mid', px[640,5])
# row brightness profile (max luminance per row) in a region without digits, x 200-240
for y in range(H):
    vals = [px[x,y] for x in range(200,240)]
    lum = [ (r+g+b)/3 for r,g,b in vals]
    print(y, round(max(lum)), round(sum(lum)/len(lum)), vals[0])
