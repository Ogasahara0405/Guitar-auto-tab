"""ギターのチューニング定数（音色モデル・ミュート確認で使用）

弦/フレット割当の本体は web/server/core/tabassign.ts（TypeScript）側にあり、
ここには DSP 側（tone.py / chords.py）が必要とする開放弦MIDIと最大フレットのみ置く。
"""

# 6弦(低音E)→1弦(高音E) の開放弦MIDI。index 0 = 6弦
TUNING_MIDI = [40, 45, 50, 55, 59, 64]
MAX_FRET = 22
