/**
 * コードラベル → ギターの押さえ方（ボイシング）。表記は6弦→1弦の順。null=ミュート
 *
 * 旧: app/core/voicing.py を移植（純ロジック・定型フォーム辞書）。
 * 押さえ方は1手で押さえられる範囲（開放弦を除くフレット開きが
 * MAX_FRET_SPAN 以内）のものだけを候補とする。
 */
import { MAX_FRET_SPAN } from "./tabassign";

export interface ShapeNote {
  string: number; // 6=低音E … 1=高音e
  fret: number;
}

export interface VoicingResult {
  shape: ShapeNote[];
  pos: number;
}

// 開放コードの定型フォーム { (ルート音名, クオリティ): [6弦..1弦] }
const OPEN_SHAPES: Record<string, (number | null)[]> = {
  "E|maj": [0, 2, 2, 1, 0, 0],
  "E|min": [0, 2, 2, 0, 0, 0],
  "E|7": [0, 2, 0, 1, 0, 0],
  "A|maj": [null, 0, 2, 2, 2, 0],
  "A|min": [null, 0, 2, 2, 1, 0],
  "A|7": [null, 0, 2, 0, 2, 0],
  "A|m7": [null, 0, 2, 0, 1, 0],
  "D|maj": [null, null, 0, 2, 3, 2],
  "D|min": [null, null, 0, 2, 3, 1],
  "D|7": [null, null, 0, 2, 1, 2],
  "C|maj": [null, 3, 2, 0, 1, 0],
  "C|7": [null, 3, 2, 3, 1, 0],
  "G|maj": [3, 2, 0, 0, 0, 3],
  "G|7": [3, 2, 0, 0, 0, 1],
  "G|min": [3, 5, 5, 3, 3, 3],
};

const PITCH_TO_PC: Record<string, number> = {
  C: 0, "C#": 1, D: 2, "D#": 3, E: 4, F: 5,
  "F#": 6, G: 7, "G#": 8, A: 9, "A#": 10, B: 11,
};
const QUALITY_PARSE: [string, string][] = [
  ["", "maj"],
  ["m7", "m7"],
  ["7", "7"],
  ["m", "min"],
];

type ShapeSlot = number | null;
type Candidate = readonly [number, ShapeSlot[]];

/** "Am" / "C#7" → (root音名, クオリティキー)。失敗時は (null, null) */
export function parseLabel(label: string): [string, string] | [null, null] {
  if (!label || label === "N.C.") return [null, null];
  const root = label.length >= 2 && label[1] === "#" ? label.slice(0, 2) : label.slice(0, 1);
  if (!(root in PITCH_TO_PC)) return [null, null];
  const suffix = label.slice(root.length);
  for (const [suf, qual] of QUALITY_PARSE) {
    if (suffix === suf) return [root, qual];
  }
  return [root, "maj"];
}

/** 開放弦を除くフレット開きが MAX_FRET_SPAN 以内（1手で押さえられる）か */
function handOk(shape: ShapeSlot[]): boolean {
  const fretted = shape.filter((f): f is number => f != null && f > 0);
  return !fretted.length || Math.max(...fretted) - Math.min(...fretted) <= MAX_FRET_SPAN;
}

/** パワーコード候補: [(ポジション, shape)] */
function powerCandidates(root: string): Candidate[] {
  const pc = PITCH_TO_PC[root];
  const out: Candidate[] = [];
  const f6 = (((pc - 40) % 12) + 12) % 12; // 6弦ルート
  const f5 = (((pc - 45) % 12) + 12) % 12; // 5弦ルート
  for (const [base, fret] of [[0, f6], [0, f6 + 12], [1, f5], [1, f5 + 12]] as const) {
    if (fret > 15) continue;
    const shape: ShapeSlot[] = [null, null, null, null, null, null];
    if (base === 0) {
      shape[0] = fret;
      shape[1] = fret + 2;
      shape[2] = fret + 2;
    } else {
      shape[1] = fret;
      shape[2] = fret + 2;
      shape[3] = fret + 2;
    }
    out.push([fret, shape]);
  }
  return out;
}

/** そのコードの押さえ方候補: [(ポジション, shape)] */
function fullCandidates(root: string, qual: string): Candidate[] {
  const out: Candidate[] = [];
  const open = OPEN_SHAPES[`${root}|${qual}`];
  if (open) out.push([0.0, [...open]]);

  const pc = PITCH_TO_PC[root];
  const f6 = (((pc - 40) % 12) + 12) % 12;
  const f5 = (((pc - 45) % 12) + 12) % 12;

  // Eフォーム・バレエコード（6弦ルート）
  if (1 <= f6 && f6 <= 12) {
    const f = f6;
    let s: ShapeSlot[];
    if (qual === "maj") s = [f, f + 2, f + 2, f + 1, f, f];
    else if (qual === "min") s = [f, f + 2, f + 2, f, f, f];
    else if (qual === "7") s = [f, f + 2, f, f + 1, f, f];
    else s = [f, f + 2, f + 2, f, f, f]; // m7 はマイナーシェイプで代用（MVP）
    out.push([f, s]);
  }

  // Aフォーム・バレエコード（5弦ルート）
  if (1 <= f5 && f5 <= 12) {
    const f = f5;
    let s: ShapeSlot[];
    if (qual === "maj") s = [null, f, f + 2, f + 2, f + 2, f];
    else if (qual === "min") s = [null, f, f + 2, f + 2, f + 1, f];
    else if (qual === "7") s = [null, f, f + 2, f + 2, f, f];
    else s = [null, f, f + 2, f + 2, f + 1, f];
    out.push([f, s]);
  }
  return out;
}

/**
 * コードラベルから押さえ方を決める。
 * chordStyle: "chord"(フルコード) / "power"(パワーコード)
 * 戻り値: shape（ミュート弦は含めない）とポジション / null
 */
export function shapeFor(
  label: string,
  chordStyle: string,
  lastPos: number,
): VoicingResult | null {
  const [root, qual] = parseLabel(label);
  if (root === null) return null;
  let cands: Candidate[] = chordStyle === "power" ? powerCandidates(root) : fullCandidates(root, qual);
  if (chordStyle !== "power" && !cands.length) cands = powerCandidates(root);
  // 1手で押さえられない押さえ方は候補から外す（無い場合は安全側で残す）
  const ok = cands.filter(([, shape]) => handOk(shape));
  if (ok.length) cands = ok;
  if (!cands.length) return null;

  let best: Candidate = cands[0];
  for (const c of cands) {
    if (Math.abs(c[0] - lastPos) < Math.abs(best[0] - lastPos)) best = c;
  }
  const [pos, shape] = best;
  return {
    shape: shape
      .map((f, i) => ({ f, i }))
      .filter(({ f }) => f != null)
      .map(({ f, i }) => ({ string: 6 - i, fret: Math.round(f as number) })),
    pos: Number(pos),
  };
}
