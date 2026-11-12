"""解析パイプライン統括: 入力 → 採譜 → タブ譜JSON + 各種出力ファイル"""
import datetime
import json
import shutil
import uuid
from pathlib import Path

import numpy as np

from . import audio, chords, melody, pdf, render, tabassign, voicing

BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = BASE_DIR / "output"


def _grid_times(y: np.ndarray, sr: int):
    """表示グリッド用のビート・小節線を計算"""
    import librosa

    tempo_arr, beats = librosa.beat.beat_track(y=y, sr=sr)
    tempo = float(np.atleast_1d(tempo_arr)[0]) or 120.0
    beat_times = [float(t) for t in librosa.frames_to_time(beats, sr=sr)]
    if len(beat_times) < 4:
        beat_dur = 60.0 / tempo
        duration = len(y) / sr
        beat_times = list(np.arange(0.0, duration, beat_dur))
    barlines = [round(t, 3) for t in beat_times[::4]]
    return tempo, [round(t, 3) for t in beat_times], barlines


def analyze(
    source: str,
    mode: str = "melody",
    chord_style: str = "chord",
    is_url: bool = False,
    title: str | None = None,
    keep_original: str | None = None,
):
    """
    解析の本体。
    mode: "melody"(単音/リード) | "chords"(コード/バッキング)
    chord_style: "chord"(フルコード) | "power"(パワーコード)  ※chordsモード時のみ
    keep_original: ブラウザ再生用に元ファイルを保持する場合のパス
    戻り値: 解析結果JSON(dict)。artifactsは output/<id>/ に保存。
    """
    if mode not in ("melody", "chords"):
        raise ValueError("mode は melody / chords のいずれかです")

    job_id = uuid.uuid4().hex[:8]
    workdir = OUTPUT_DIR / job_id
    workdir.mkdir(parents=True, exist_ok=True)

    if is_url:
        wav_path, dl_title = audio.download_youtube(source, str(workdir))
        title = title or dl_title
    else:
        wav_path = audio.ensure_wav(source, str(workdir / "source.wav"))
        title = title or Path(source).stem

    y, sr = audio.load_audio(wav_path)
    duration = float(len(y) / sr)
    tempo, beats, barlines = _grid_times(y, sr)

    result = {
        "meta": {
            "title": title,
            "duration": round(duration, 3),
            "tempo": round(tempo, 2),
            "mode": mode,
            "tuning": "EADGBE",
            "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        },
        "notes": [],
        "chords": [],
        "beats": beats,
        "barlines": barlines,
    }

    if mode == "melody":
        notes = melody.extract_notes(y, sr)
        result["notes"] = tabassign.assign_frets(notes)
    else:
        ch = chords.extract_chords(y, sr)
        result["meta"]["tempo"] = round(ch["tempo"], 2)
        last_pos = 0.0
        for c in ch["chords"]:
            if c["label"] == "N.C.":
                continue
            v = voicing.shape_for(c["label"], chord_style, last_pos)
            if v is None:
                continue
            last_pos = v["pos"]
            result["chords"].append(
                {"start": c["start"], "end": c["end"], "label": c["label"], "shape": v["shape"]}
            )

    # ブラウザで動画/音声を再生できるよう元ファイルも保持
    if keep_original and not is_url:
        ext = Path(keep_original).suffix or ".bin"
        media_name = f"source_original{ext}"
        shutil.copyfile(keep_original, workdir / media_name)
        result["meta"]["media_file"] = media_name

    _save_artifacts(result, job_id, workdir)
    result["id"] = job_id
    return result


def import_analysis(json_path: str):
    """
    Claude Codeで磨いた analysis.json を取り込み、ジョブとして登録する
    （表示・PDF/TXT出力を同じ流れで行えるようにする）
    """
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    if "meta" not in data:
        raise ValueError("meta を含む解析結果JSONを指定してください")
    job_id = uuid.uuid4().hex[:8]
    workdir = OUTPUT_DIR / job_id
    workdir.mkdir(parents=True, exist_ok=True)
    _save_artifacts(data, job_id, workdir)
    data["id"] = job_id
    return data


def _save_artifacts(result: dict, job_id: str, workdir: Path):
    (workdir / "analysis.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (workdir / "tab.txt").write_text(render.score_to_ascii(result), encoding="utf-8")
    pdf.render_pdf(result, str(workdir / "tab.pdf"))
