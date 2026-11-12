"""タブ譜のPDF出力（reportlabによるベクタ描画・日本語対応）"""
import os

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas

from .grid import build_score

STAFF_GAP = 3.2 * mm
SLOT_W = 3.4 * mm
CELL_H = 11 * mm

# Windowsの日本語TTFを埋め込み。無ければCIDフォントへフォールバック
_WIN_FONTS = [
    ("YuGothic", "C:/Windows/Fonts/YuGothM.ttc"),
    ("YuGothic", "C:/Windows/Fonts/YuGothR.ttc"),
    ("Meiryo", "C:/Windows/Fonts/meiryo.ttc"),
    ("MS-Gothic", "C:/Windows/Fonts/msgothic.ttc"),
]


def _pick_font() -> str:
    for name, path in _WIN_FONTS:
        if not os.path.exists(path):
            continue
        try:
            pdfmetrics.registerFont(TTFont(name, path, subfontIndex=0))
            return name
        except Exception:
            continue
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
        return "HeiseiKakuGo-W5"
    except Exception:
        return "Helvetica"


def render_pdf(result: dict, out_path: str):
    font = _pick_font()
    meta = result.get("meta", {})
    score = build_score(result)
    measures, events, labels = score["measures"], score["events"], score["labels"]

    page = landscape(A4)
    c = rl_canvas.Canvas(out_path, pagesize=page)
    W, H = page
    margin_x = 14 * mm
    usable_w = W - margin_x * 2

    def measure_w(m) -> float:
        return (m["slots"] + 2) * SLOT_W  # スロット + 左右のバー線余白

    per_system = max(1, int(usable_w // measure_w(measures[0])))
    systems = [measures[i: i + per_system] for i in range(0, len(measures), per_system)]

    # ヘッダ
    c.setFont(font, 14)
    c.drawString(margin_x, H - 16 * mm, str(meta.get("title", "(無題)")))
    c.setFont(font, 9)
    mode = "メロディ(単音)" if meta.get("mode") == "melody" else "コード(バッキング)"
    c.drawString(
        margin_x,
        H - 22 * mm,
        f"{mode}   tempo={meta.get('tempo', '?')} BPM   tuning=EADGBE",
    )

    y = H - 34 * mm
    page_no = 1
    sys_top_idx = 0

    for sys in systems:
        if y < 24 * mm:
            c.setFont(font, 8)
            c.drawRightString(W - margin_x, 10 * mm, str(page_no))
            c.showPage()
            page_no += 1
            y = H - 18 * mm

        top = y
        staff_w = sum(measure_w(m) for m in sys)

        # 6本の譜線（1弦=上）
        c.setLineWidth(0.6)
        for r in range(6):
            yy = top - r * STAFF_GAP
            c.line(margin_x, yy, margin_x + staff_w, yy)

        # 小節線
        x = margin_x
        bar_xs = [x]
        for m in sys:
            x += measure_w(m)
            bar_xs.append(x)
        c.setLineWidth(0.9)
        for bx in bar_xs:
            c.line(bx, top, bx, top - 5 * STAFF_GAP)

        def pos_x(measure_idx_global: int, slot: int) -> float:
            local = measure_idx_global - sys_top_idx
            base = margin_x + sum(measure_w(m) for m in sys[:local])
            return base + (slot + 1.5) * SLOT_W

        # ノート/コードのフレット数字
        c.setFont(font, 8)
        for ev in events:
            if not (sys_top_idx <= ev["measure"] < sys_top_idx + len(sys)):
                continue
            x = pos_x(ev["measure"], ev["slot"])
            for row, text in ev["cells"].items():
                c.drawCentredString(x, top - row * STAFF_GAP - 2.2, str(text))

        # コード名
        c.setFont(font, 9)
        for lb in labels:
            if not (sys_top_idx <= lb["measure"] < sys_top_idx + len(sys)):
                continue
            x = pos_x(lb["measure"], lb["slot"])
            c.drawString(x - 3, top + 3.2 * mm, lb["text"])

        y = top - CELL_H
        sys_top_idx += len(sys)

    c.setFont(font, 8)
    c.drawRightString(W - margin_x, 10 * mm, str(page_no))
    c.save()
