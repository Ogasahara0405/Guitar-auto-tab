import sys, os, site
sys.path.append(site.getusersitepackages())
from PIL import Image
src = sys.argv[1]
im = Image.open(src).convert('RGB')
W,H = im.size
px = im.load()
x0, x1 = int(sys.argv[2]), int(sys.argv[3])
for x in range(x0, x1):
    # average color over y=35..145
    rs=gs=bs=0; n=0
    mx = 0
    for y in range(35,145):
        r,g,b = px[x,y]
        rs+=r; gs+=g; bs+=b; n+=1
        lum=(r+g+b)/3
        if lum>mx: mx=lum
    print(x, (rs//n, gs//n, bs//n), 'maxlum', round(mx))
