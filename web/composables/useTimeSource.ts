/**
 * 再生位置（秒）を返す関数の共有（プレイヤーが差し替えられるため ref 風に保持）
 */
export type TimeSource = { current: (() => number) | null };

export function useTimeSource(): TimeSource {
  return { current: null };
}
