import json

def ev(x, *notes):
    return {"x": x, "notes": [{"string": s, "fret": f} for s, f in notes]}

# Layout A: frames 71-74
events_A = [
    ev(47, (5, 5)),
    ev(75, (5, 4)),
    ev(135, (6, 0)),
    ev(191, (6, 1)),
    ev(295, (5, 4), (6, 2)),
    ev(396, (5, 2), (6, 0)),
    ev(525, (4, 7), (5, 6)),
    ev(639, (5, 9), (6, 7)),
    ev(667, (5, 9), (6, 7)),
    ev(735, (4, 9), (5, 7)),
    ev(762, (4, 9), (5, 7)),
    ev(859, (4, 2), (5, 0)),
    ev(899, (4, 2), (5, 0)),
    ev(926, (4, 2), (5, 0)),
    ev(974, (5, 0)),
    ev(1002, (5, 2)),
    ev(1077, (4, 6), (5, 4)),
    ev(1115, (4, 6), (5, 4)),
    ev(1143, (4, 6), (5, 4)),
    ev(1257, (4, 7), (5, 5)),
]

# Layout B: frames 75-77
events_B = [
    ev(22, (4, 2), (5, 0)),
    ev(49, (4, 2), (5, 0)),
    ev(97, (5, 0)),
    ev(125, (5, 2)),
    ev(200, (4, 6), (5, 4)),
    ev(239, (4, 6), (5, 4)),
    ev(267, (4, 6), (5, 4)),
    ev(381, (4, 7), (5, 5)),
    ev(423, (4, 7), (5, 5)),
    ev(453, (4, 7), (5, 5)),
    ev(504, (5, 5)),
    ev(533, (5, 4)),
    ev(593, (4, 9), (5, 7)),
    ev(651, (4, 10), (5, 8)),
    ev(757, (4, 11), (5, 9)),
    ev(857, (4, 9), (5, 7)),
    ev(986, (4, 7), (5, 6)),
    ev(1095, (4, 7), (5, 5)),
    ev(1150, (4, 6), (5, 4)),
    ev(1195, (4, 7), (5, 6)),
    ev(1229, (4, 10), (5, 8)),
]

# Layout C: frames 78-82
events_C = [
    ev(107, (4, 7), (5, 6)),
    ev(216, (4, 7), (5, 5)),
    ev(271, (4, 6), (5, 4)),
    ev(317, (4, 7), (5, 6)),
    ev(350, (4, 10), (5, 8)),
    ev(445, (4, 11), (5, 9)),
    ev(550, (4, 11), (5, 8)),
    ev(661, (4, 9), (5, 7)),
    ev(790, (4, 9), (5, 6)),
    ev(906, (4, 4), (5, 2)),
    ev(1035, (4, 6), (5, 4)),
    ev(1135, (4, 7), (5, 5)),
    ev(1257, (5, 5), (6, 3)),
]

# Layout D: frames 83-84
events_D = [
    ev(26, (4, 4), (5, 2)),
    ev(155, (4, 6), (5, 4)),
    ev(255, (4, 7), (5, 5)),
    ev(376, (5, 5), (6, 3)),
    ev(432, (4, 7), (5, 5)),
    ev(459, (4, 9), (5, 7)),
    ev(665, (1, 8)),
    ev(694, (1, 12)),
    ev(722, (1, 12)),
    ev(783, (1, 12)),
    ev(815, (1, 10)),
    ev(846, (1, 8)),
    ev(879, (1, 7)),
    ev(907, (1, 8)),
    ev(935, (1, 10)),
    ev(963, (1, 10)),
    ev(1023, (1, 10)),
    ev(1062, (1, 8)),
    ev(1090, (1, 7)),
    ev(1146, (2, 8)),
    ev(1174, (2, 10)),
    ev(1202, (2, 8)),
    ev(1263, (2, 8)),  # ghost note (8)
]

def notes(*pairs):
    return [{"string": s, "fret": f} for s, f in pairs]

frames = [
    {"n": 71, "cursor_notes": [], "events": events_A},
    {"n": 72, "cursor_notes": [], "events": events_A},
    {"n": 73, "cursor_notes": [], "events": events_A},
    {"n": 74, "cursor_notes": [], "events": events_A},
    {"n": 75, "cursor_notes": [], "events": events_B},
    {"n": 76, "cursor_notes": notes((4, 10), (5, 8)), "events": events_B},
    {"n": 77, "cursor_notes": [], "events": events_B},
    {"n": 78, "cursor_notes": [], "events": events_C},
    {"n": 79, "cursor_notes": [], "events": events_C},
    {"n": 80, "cursor_notes": [], "events": events_C},
    {"n": 81, "cursor_notes": [], "events": events_C},
    {"n": 82, "cursor_notes": [], "events": events_C},
    {"n": 83, "cursor_notes": [], "events": events_D},
    {"n": 84, "cursor_notes": notes((5, 5), (6, 3)), "events": events_D},
]

out = {"frames": frames}
s = json.dumps(out, indent=1)
print(s)
with open(r"C:\Users\iniad\Documents\個人開発\Guitar-auto-tab\_ref\tabframes_zoom\result_71_84.json", "w", encoding="utf-8") as f:
    f.write(s)
print("OK", sum(len(fr["events"]) for fr in frames), "events total")
