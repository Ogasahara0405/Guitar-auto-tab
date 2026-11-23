import sys, os, site
sys.path.append(site.getusersitepackages())
from PIL import Image
src = sys.argv[1]
x0, y0, x1, y1 = [int(v) for v in sys.argv[2:6]]
im = Image.open(src).convert('L')
px = im.load()
ramp = ' .:-=+*#%@'
print('    ' + ''.join(str((x0+i)//100%10) for i in range(x1-x0)))
print('    ' + ''.join(str((x0+i)//10%10) for i in range(x1-x0)))
print('    ' + ''.join(str((x0+i)%10) for i in range(x1-x0)))
for y in range(y0, y1):
    row = ''
    for x in range(x0, x1):
        v = px[x, y]
        idx = min(9, max(0, (v - 15) * 9 // 190))
        row += ramp[idx]
    print(f'{y:3d} {row}')
