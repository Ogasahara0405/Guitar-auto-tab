import type { ChordStyle, Mode } from "../api";

interface Props {
  mode: Mode;
  chordStyle: ChordStyle;
  onModeChange: (m: Mode) => void;
  onChordStyleChange: (s: ChordStyle) => void;
}

export default function ModeSelector({ mode, chordStyle, onModeChange, onChordStyleChange }: Props) {
  return (
    <div className="row">
      <div className="group">
        <label>出力したいパート</label>
        <div className="radios">
          <label>
            <input
              type="radio"
              name="mode"
              checked={mode === "melody"}
              onChange={() => onModeChange("melody")}
            />
            メロディ（単音・リード）
          </label>
          <label>
            <input
              type="radio"
              name="mode"
              checked={mode === "chords"}
              onChange={() => onModeChange("chords")}
            />
            コード（バッキング）
          </label>
        </div>
      </div>

      {mode === "chords" && (
        <div className="group">
          <label>バッキングの出力形式</label>
          <div className="radios">
            <label>
              <input
                type="radio"
                name="chord_style"
                checked={chordStyle === "chord"}
                onChange={() => onChordStyleChange("chord")}
              />
              コード
            </label>
            <label>
              <input
                type="radio"
                name="chord_style"
                checked={chordStyle === "power"}
                onChange={() => onChordStyleChange("power")}
              />
              パワーコード
            </label>
          </div>
        </div>
      )}
    </div>
  );
}
