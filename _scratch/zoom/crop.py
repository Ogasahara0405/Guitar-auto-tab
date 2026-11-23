import sys, os, site
sys.path.append(site.getusersitepackages())
from PIL import Image
src, out = sys.argv[1], sys.argv[2]
x0, y0, x1, y1, scale = [int(v) for v in sys.argv[3:8]]
im = Image.open(src)
print('size', im.size)
c = im.crop((x0, y0, x1, y1))
w, h = c.size
c = c.resize((w*scale, h*scale), Image.LANCZOS)
c.save(out)
print('saved', out, c.size)
