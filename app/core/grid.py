"""タブ譜のグリッド配置（ASCII描画・PDF描画の共通レイアウト計算）"""
import bisect

from .tabassign import GROUP_TOL


def build_score(result: dict, slots_per_beat: int | None = None):
    """
    解析結果JSON → 描画用スコア情報。
    row 0 = 1弦(高音e/上) ... row 5 = 6弦(低音E/下)
    戻り値:
      measures: [{start, end, slots}]
      events:   [{measure, slot, cells: {row: text}, label: str|None}]
      labels:   [{measure, slot, text}]   … コード名など譜面上部の文字
    """
    meta = result.get("meta", {})
    duration = float(meta.get("duration", 0.0))
    tempo = float(meta.get("tempo") or 120.0)
    beat_dur = 60.0 / max(tempo, 1.0)

    barlines = list(result.get("barlines") or [])
    if not barlines or barlines[0] > 0.05:
        barlines = [0.0] + barlines
    if barlines[-1] < duration - 0.05:
        barlines.append(duration)

    notes = result.get("notes") or []
    chords = result.get("chords") or []

    if slots_per_beat is None:
        # ノート密度が高いときは16分グリッドへ
        if notes and duration > 0 and len(notes) / duration > 3.5:
            slots_per_beat = 4
        else:
            slots_per_beat = 2

    measures = []
    for a, b in zip(barlines[:-1], barlines[1:]):
        if b - a <= 0.01:
            continue
        slots = max(2, round((b - a) / beat_dur * slots_per_beat))
        measures.append({"start": float(a), "end": float(b), "slots": int(slots)})
    if not measures:
        measures = [{"start": 0.0, "end": max(duration, 1.0), "slots": 8}]

    bounds = [m["start"] for m in measures]
    occupied = [set() for _ in measures]
    events = []
    labels = []

    def place(t: float):
        mi = bisect.bisect_right(bounds, t) - 1
        mi = max(0, min(mi, len(measures) - 1))
        m = measures[mi]
        pos = (t - m["start"]) / max(m["end"] - m["start"], 1e-6)
        slot = round(pos * (m["slots"] - 1))
        slot = max(0, min(slot, m["slots"] - 1))
        while slot in occupied[mi] and slot < m["slots"] - 1:
            slot += 1
        occupied[mi].add(slot)
        return mi, slot

    # 開始時刻がほぼ同じノートは同時発音として1イベント（複数弦のセル）にまとめる
    note_groups = []
    for n in sorted(notes, key=lambda x: x.get("start", 0.0)):
        if "string" not in n or "fret" not in n:
            continue
        row = int(n["string"]) - 1  # 1弦→row0(上)
        if not (0 <= row <= 5):
            continue
        if note_groups and float(n["start"]) - note_groups[-1][0] <= GROUP_TOL:
            note_groups[-1][1][row] = str(int(n["fret"]))
        else:
            note_groups.append((float(n["start"]), {row: str(int(n["fret"]))}))

    for start_t, cells in note_groups:
        mi, slot = place(start_t)
        events.append(
            {
                "measure": mi,
                "slot": slot,
                "cells": cells,
                "label": None,
            }
        )

    for c in chords:
        shape = c.get("shape") or []
        if shape:
            mi, slot = place(float(c["start"]))
            cells = {}
            for st in shape:
                row = int(st["string"]) - 1
                if 0 <= row <= 5:
                    cells[row] = str(int(st["fret"]))
            events.append(
                {
                    "measure": mi,
                    "slot": slot,
                    "cells": cells,
                    "label": c.get("label"),
                }
            )
        if c.get("label") and c["label"] != "N.C.":
            mi, slot = place(float(c["start"]))
            labels.append({"measure": mi, "slot": slot, "text": c["label"]})

    return {
        "measures": measures,
        "events": events,
        "labels": labels,
        "slots_per_measure_max": max(m["slots"] for m in measures),
    }
