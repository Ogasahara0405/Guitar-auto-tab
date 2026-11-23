import sys, os, site
sys.path.append(site.getusersitepackages())
from PIL import Image
for n in [int(v) for v in sys.argv[1:]]:
    src = f'C:/Users/iniad/Documents/個人開発/Guitar-auto-tab/_ref/tabframes/tf_{n:04d}.jpg'
    imr = Image.open(src).convert('RGB')
    for hi, (hx0, hx1) in enumerate([(0, 640), (640, 1280)]):
        crop = imr.crop((hx0, 30, hx1, 160))
        w, h = crop.size
        crop.resize((int(w * 2.4), int(h * 2.4)), Image.LANCZOS).save(f'half_{n:04d}_{hi}.png')
    print('saved', n)
