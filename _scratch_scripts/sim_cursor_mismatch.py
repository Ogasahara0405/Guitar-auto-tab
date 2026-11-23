# Simulation of TabViewer tick/setActive vs timeToX system mismatch.
# Faithful port of web/shared/grid.ts buildScore, web/shared/tabLayout.ts buildTabLayout,
# and web/components/TabViewer.vue tick()/setActive() logic.
# Run: python -I sim_cursor_mismatch.py <analysis.json> [containerWidth]
import json
import math
import sys

SLOT_W = 14


def js_round(x):
    # JS Math.round: floor(x + 0.5) for positive x (all ours are >= 0)
    return math.floor(x + 0.5)


def build_score(result):
    meta = result["meta"]
    duration = float(meta.get("duration") or 0.0)
    tempo = float(meta.get("tempo") or 120.0)
    beat_dur = 60.0 / max(tempo, 1.0)

    barlines = list(result.get("barlines") or [])
    if not barlines or barlines[0] > 0.05:
        barlines = [0.0] + barlines
    if barlines[-1] < duration - 0.05:
        barlines.append(duration)

    notes = result.get("notes") or []
    slots_per_beat = 4 if (notes and duration > 0 and len(notes) / duration > 3.5) else 2

    measures = []
    for i in range(len(barlines) - 1):
        a, b = barlines[i], barlines[i + 1]
        if b - a <= 0.01:
            continue
        slots = max(2, js_round(((b - a) / beat_dur) * slots_per_beat))
        measures.append({"start": a, "end": b, "slots": slots})
    if not measures:
        measures.append({"start": 0.0, "end": max(duration, 1.0), "slots": 8})

    bounds = [m["start"] for m in measures]
    occupied = [set() for _ in measures]
    events = []

    def place(t):
        mi = 0
        for i in range(len(bounds)):
            if bounds[i] <= t:
                mi = i
        mi = max(0, min(mi, len(measures) - 1))
        m = measures[mi]
        pos = (t - m["start"]) / max(m["end"] - m["start"], 1e-6)
        slot = js_round(pos * (m["slots"] - 1))
        slot = max(0, min(slot, m["slots"] - 1))
        while slot in occupied[mi] and slot < m["slots"] - 1:
            slot += 1
        occupied[mi].add(slot)
        return mi, slot

    assigned = [n for n in notes if n.get("string") is not None and n.get("fret") is not None]
    assigned.sort(key=lambda n: n["start"])
    # groupByStart (GROUP_TOL = 0.05, compared against group's first start)
    groups = []
    for it in assigned:
        if groups and it["start"] - groups[-1][0]["start"] <= 0.05:
            groups[-1].append(it)
        else:
            groups.append([it])
    for g in groups:
        mi, slot = place(g[0]["start"])
        events.append({"measure": mi, "slot": slot})

    return measures, events, slots_per_beat, duration


def measure_time_of(m, slot):
    pos = slot / (m["slots"] - 1) if m["slots"] > 1 else 0.0
    return m["start"] + pos * (m["end"] - m["start"])


def build_layout(measures, events, container_width):
    per_system = max(1, math.floor((container_width - 24) / ((measures[0]["slots"] + 2) * SLOT_W)))
    per_system = min(per_system, 8)

    sorted_events = sorted(events, key=lambda e: (measures[e["measure"]]["start"], e["slot"]))
    laid = []
    for i, ev in enumerate(sorted_events):
        m = measures[ev["measure"]]
        laid.append({
            "index": i,
            "system": ev["measure"] // per_system,
            "measure": ev["measure"],
            "slot": ev["slot"],
            "time": measure_time_of(m, ev["slot"]),
            "mstart": m["start"],
            "mend": m["end"],
        })
    return laid, per_system


def time_to_x_system(t, measures, per_system):
    for mi, m in enumerate(measures):
        if m["start"] <= t < m["end"]:
            return mi // per_system, mi
    return None, None


def simulate(result, container_width, fps=60.0):
    measures, events, spb, duration = build_score(result)
    laid, per_system = build_layout(measures, events, container_width)
    if not laid:
        print("  (no events)")
        return

    n_systems = (len(measures) + per_system - 1) // per_system
    print(f"  measures={len(measures)} events={len(laid)} perSystem={per_system} systems={n_systems}")

    # first event slot of each system's first measure (for reporting)
    first_ev_by_system = {}
    for ev in laid:
        if ev["system"] not in first_ev_by_system:
            first_ev_by_system[ev["system"]] = ev

    dt = 1.0 / fps
    windows = []  # contiguous mismatch windows: (t_start, t_end, disp_sys, x_sys)
    cur = None
    t = 0.0
    idx = -1
    while t <= duration + dt:
        # tick: idx = last i with ev.time <= t + 0.02
        while idx + 1 < len(laid) and laid[idx + 1]["time"] <= t + 0.02:
            idx += 1
        disp_sys = laid[idx]["system"] if idx >= 0 else -1
        x_sys, mi = time_to_x_system(t, measures, per_system)
        mismatch = idx >= 0 and x_sys is not None and disp_sys != x_sys
        if mismatch:
            if cur is None:
                cur = [t, t, disp_sys, x_sys]
            else:
                cur[1] = t
        else:
            if cur is not None:
                windows.append(tuple(cur))
                cur = None
        t += dt
    if cur is not None:
        windows.append(tuple(cur))

    # merge tiny gaps (< 3 frames) caused by discretization at slot-0 events
    merged = []
    for w in windows:
        if merged and w[0] - merged[-1][1] < 3 * dt and w[2] == merged[-1][2] and w[3] == merged[-1][3]:
            merged[-1] = (merged[-1][0], w[1], w[2], w[3])
        else:
            merged.append(w)

    total = sum(w[1] - w[0] for w in merged)
    print(f"  mismatch windows: {len(merged)}, total frozen time: {total:.2f}s")
    for w in merged:
        t0, t1, disp_sys, x_sys = w
        dur = t1 - t0
        fe = first_ev_by_system.get(x_sys)
        fe_info = f"newsys first ev: measure={fe['measure']} slot={fe['slot']} (m.slots={measures[fe['measure']]['slots']}) time={fe['time']:.2f}" if fe else "newsys EMPTY (no events)"
        m0 = x_sys * per_system
        m_info = f"newsys first measure={m0} start={measures[m0]['start']:.2f}" if m0 < len(measures) else "?"
        print(f"    t=[{t0:7.2f},{t1:7.2f}] dur={dur:5.2f}s  visible cursor frozen on system {disp_sys}, x tracked on system {x_sys} | {m_info} | {fe_info}")


if __name__ == "__main__":
    path = sys.argv[1]
    widths = [float(x) for x in sys.argv[2:]] or [1100]
    with open(path, encoding="utf-8") as f:
        result = json.load(f)
    print(f"=== {path} ===")
    for w in widths:
        print(f"-- containerWidth={w}")
        simulate(result, w)
