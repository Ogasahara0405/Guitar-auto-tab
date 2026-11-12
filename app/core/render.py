"""タブ譜のASCIIテキスト出力（Ultimate Guitar風）"""
from .grid import build_score

STRING_NAMES = ["e", "B", "G", "D", "A", "E"]  # 上から1弦..6弦
CELL_W = 4
MEASURES_PER_LINE = 4


def score_to_ascii(result: dict) -> str:
    score = build_score(result)
    measures = score["measures"]
    events = score["events"]
    labels = score["labels"]
    meta = result.get("meta", {})

    lines = []
    lines.append(f"# {meta.get('title', '(無題)')}")
    tempo = meta.get("tempo", "?")
    if meta.get("mode") == "melody":
        lines.append(f"# メロディ(単音) / tempo={tempo} BPM / tuning=EADGBE")
    else:
        lines.append(f"# コード(バッキング) / tempo={tempo} BPM")
    lines.append("")

    for line_start in range(0, len(measures), MEASURES_PER_LINE):
        chunk = measures[line_start: line_start + MEASURES_PER_LINE]

        # 1小節 = [バー線1列 + スロット slots列]。最終小節の後ろに締めバー線が1列
        measure_widths = [m["slots"] + 1 for m in chunk]
        total_cols = sum(measure_widths) + 1

        rows = [["-"] * (total_cols * CELL_W) for _ in range(6)]
        label_line = [" "] * (total_cols * CELL_W)

        # バー線の列位置
        bar_cols = []
        col = 0
        for w in measure_widths:
            bar_cols.append(col)
            col += w
        bar_cols.append(col)  # 締め
        for bc in bar_cols:
            x = bc * CELL_W + CELL_W // 2
            for r in range(6):
                rows[r][x] = "|"

        def cell_x(measure_idx: int, slot: int) -> int:
            base = sum(measure_widths[: measure_idx - line_start]) + 1
            return (base + slot) * CELL_W

        for ev in events:
            if not (line_start <= ev["measure"] < line_start + len(chunk)):
                continue
            x0 = cell_x(ev["measure"], ev["slot"])
            for row, text in ev["cells"].items():
                text = str(text)[: CELL_W - 1]
                pad = (CELL_W - 1 - len(text)) // 2
                for k, ch in enumerate(text):
                    x = x0 + pad + k
                    if 0 <= x < total_cols * CELL_W:
                        rows[row][x] = ch

        for lb in labels:
            if not (line_start <= lb["measure"] < line_start + len(chunk)):
                continue
            x0 = cell_x(lb["measure"], lb["slot"])
            for k, ch in enumerate(lb["text"]):
                x = x0 + k
                if 0 <= x < len(label_line):
                    label_line[x] = ch

        if any(c != " " for c in label_line):
            lines.append("".join(label_line).rstrip())
        for r in range(6):
            lines.append(f"{STRING_NAMES[r]}|{''.join(rows[r])}")
        lines.append("")

    return "\n".join(lines) + "\n"
