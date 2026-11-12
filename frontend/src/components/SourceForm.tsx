import { useState } from "react";

interface Props {
  url: string;
  busy: boolean;
  onUrlChange: (v: string) => void;
  onAnalyze: (file: File | null) => void;
}

export default function SourceForm({ url, busy, onUrlChange, onAnalyze }: Props) {
  const [file, setFile] = useState<File | null>(null);

  return (
    <div className="row">
      <div className="group grow">
        <label htmlFor="url">YouTube URL</label>
        <input
          id="url"
          type="text"
          placeholder="https://www.youtube.com/watch?v=..."
          value={url}
          onChange={(e) => onUrlChange(e.target.value)}
        />
      </div>
      <div className="group">
        <label htmlFor="file">または ファイル</label>
        <input
          id="file"
          type="file"
          accept="audio/*,video/*"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </div>
      <button className="primary" disabled={busy} onClick={() => onAnalyze(file)}>
        解析開始
      </button>
    </div>
  );
}
