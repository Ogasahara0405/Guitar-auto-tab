/**
 * メロディ採譜の不要音クリーニング
 *
 * ミックス音声（バックの原曲・ベース・ボーカルの混入）から採譜すると、
 * 極端に短い断片や根拠の弱い副次声が多数混ざる。chordauto 等の
 * 「出力に不要音を乗せない」方針に合わせ、タブ譜に乗せる前に落とす:
 *
 * 1. 断片ノート（MIN_DURATION 未満）— ピッチ追跡の切れ端・ノイズ
 * 2. 弱い短音（SHORT_DURATION 未満 かつ evidence が弱いもの）
 * 3. 副次声の整理（時間的に重なるクラスタ内）:
 *    - 主音（evidence が厳密に 1.0 = melody.py の不変条件）以外の声を対象にする
 *    - 主音と開始時刻が SIMULTANEOUS_WINDOW 以内＝「同時に弾いた声」
 *      （ダブルストップ・オクターブ・小コード）は、控えめな根拠でも残す
 *    - 開始が大きくずれて重なるだけの声（混入音の倍音が後から立ち上がる
 *      実測パターン）は、根拠が強い場合のみ残す
 *    - 主音が1つも無いクラスタ（tone除去で主音だけ落ちた孤児）は厳しく扱う
 *
 * 前提の不変条件: worker/melody.py は主音を常に evidence=1.0 で出力し、
 * 副次声のみ evidence<1.0（サリエンス比・オクターブ過剰比、下限0.3）になる。
 * 本物のオクターブ・ダブルストップは開始がほぼ揃う（1回のピッキング/ストローク）。
 */
import type { PerceptionNote } from "../../shared/schema";

/** これ未満のノートは断片として除去（秒） */
export const MIN_DURATION = 0.07;
/** これ未満のノートは、根拠が強い場合のみ残す（秒） */
export const SHORT_DURATION = 0.12;
/** 非同時の副次声・孤児クラスタに要求する evidence */
export const STRICT_EVIDENCE = 0.5;
/** 同時に弾かれた副次声に要求する evidence（本物の控えめな同時発音を守る） */
export const SIMULTANEOUS_EVIDENCE = 0.4;
/** 同時発音とみなす主音との開始時刻差（秒） */
export const SIMULTANEOUS_WINDOW = 0.1;
/** クラスタを同一視する実時間的な重なり（秒） */
export const OVERLAP_MIN = 0.05;
/** melody.py が主音に出す evidence（厳密な1.0）とみなすしきい値 */
export const PRIMARY_EVIDENCE = 0.999;

export interface CleanInfo {
  dropped: number;
}

interface Cluster {
  notes: PerceptionNote[];
  start: number;
  end: number;
}

function overlap(a: PerceptionNote | Cluster, b: PerceptionNote | Cluster): number {
  return Math.min(a.end, b.end) - Math.max(a.start, b.start);
}

/** 時間的に重なるノート（実時間 OVERLAP_MIN 以上）を1つのクラスタにまとめる */
function clusterByOverlap(notes: PerceptionNote[]): Cluster[] {
  const clusters: Cluster[] = [];
  for (const n of [...notes].sort((a, b) => a.start - b.start || a.midi - b.midi)) {
    const hit = clusters.find((c) => overlap(c, n) >= OVERLAP_MIN);
    if (hit) {
      hit.notes.push(n);
      hit.start = Math.min(hit.start, n.start);
      hit.end = Math.max(hit.end, n.end);
    } else {
      clusters.push({ notes: [n], start: n.start, end: n.end });
    }
  }
  return clusters;
}

/**
 * メロディの不要音を除去する（音源分離・音色フィルタの後の仕上げ）。
 * 戻り値: (クリーンなノート, 除去数)。ノート自体は変更しない。
 */
export function cleanMelodyNotes(notes: PerceptionNote[]): [PerceptionNote[], number] {
  let dropped = 0;

  // --- 規則1・2: 断片と弱い短音 ---
  const kept: PerceptionNote[] = [];
  for (const n of notes) {
    const dur = n.end - n.start;
    const ev = n.evidence ?? 1.0;
    if (dur < MIN_DURATION) {
      dropped += 1;
      continue;
    }
    if (dur < SHORT_DURATION && ev < STRICT_EVIDENCE) {
      dropped += 1;
      continue;
    }
    kept.push(n);
  }

  // --- 規則3: クラスタ内の副次声を整理 ---
  const out: PerceptionNote[] = [];
  for (const cluster of clusterByOverlap(kept)) {
    const sorted = [...cluster.notes].sort(
      (a, b) => (b.evidence ?? 1) - (a.evidence ?? 1) || a.midi - b.midi,
    );
    const primary = sorted[0];
    const hasPrimary = (primary.evidence ?? 1) >= PRIMARY_EVIDENCE;

    for (const n of sorted) {
      if (n === primary && hasPrimary) {
        out.push(n); // 主音は必ず残す
        continue;
      }
      const ev = n.evidence ?? 1.0;
      // 同時に弾かれた声（開始が主音と近い）は控えめな根拠でも残す。
      // 主音の無いクラスタは孤児（主音が tone 除去等で先に落ちた跡）なので厳しく扱う。
      const simultaneous =
        hasPrimary && Math.abs(n.start - primary.start) <= SIMULTANEOUS_WINDOW;
      const need = simultaneous ? SIMULTANEOUS_EVIDENCE : STRICT_EVIDENCE;
      if (ev < need) {
        dropped += 1;
        continue;
      }
      out.push(n);
    }
  }

  out.sort((a, b) => a.start - b.start || a.midi - b.midi);
  return [out, dropped];
}
