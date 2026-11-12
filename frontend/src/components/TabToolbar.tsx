import type { AnalysisResult } from "../types";
import { jobUrl } from "../api";
import type { ArtifactName } from "../api";

interface Props {
  result: AnalysisResult;
  onImport: (file: File) => void;
}

export default function TabToolbar({ result, onImport }: Props) {
  const modeLabel = result.meta.mode === "melody" ? "メロディ(単音)" : "コード(バッキング)";
  const title = `${result.meta.title} — ${modeLabel} / ${result.meta.tempo} BPM`;

  const save = (name: ArtifactName) => {
    window.location.href = jobUrl(result.id, name);
  };

  return (
    <div className="tab-toolbar">
      <span className="tab-title">{title}</span>
      <div className="spacer" />
      <button onClick={() => save("tab.pdf")}>PDF保存</button>
      <button onClick={() => save("tab.txt")}>TXT保存</button>
      <button onClick={() => save("analysis.json")}>analysis.json書き出し</button>
      <label className="file-btn">
        磨き上げJSONを取り込み
        <input
          type="file"
          accept=".json,application/json"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onImport(f);
            e.target.value = "";
          }}
        />
      </label>
    </div>
  );
}
