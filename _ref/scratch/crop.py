import sys, os
from PIL import Image

src_dir = r'C:/Users/iniad/Documents/個人開発/Guitar-auto-tab/_ref/tabframes'
out_dir = r'C:/Users/iniad/Documents/個人開発/Guitar-auto-tab/_ref/crops'

for n in sys.argv[1:]:
    n = int(n)
    im = Image.open(os.path.join(src_dir, 'tf_%04d.jpg' % n))
    w, h = im.size
    # 4 overlapping horizontal strips, 4x upscale
    step = w // 4
    for i in range(4):
        x0 = max(0, i * step - 20)
        x1 = min(w, (i + 1) * step + 40)
        crop = im.crop((x0, 0, x1, h))
        crop = crop.resize((crop.width * 4, crop.height * 4), Image.LANCZOS)
        crop.save(os.path.join(out_dir, 'f%04d_s%d.png' % (n, i)))
    print('done', n)
