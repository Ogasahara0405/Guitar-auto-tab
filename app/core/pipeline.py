"""解析パイプライン統括: 入力 → 採譜 → タブ譜JSON + 各種出力ファイル"""
import datetime
import json
import shutil
import uuid
from pathlib import Path

import numpy as np

from . import audio, chords, melody, pdf, render, sep, tabassign, video, voicing

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


def _is_usable_stem(stem_wav: str, mix_wav: str) -> bool:
    """分離ステムに十分なギター成分が含まれるか（ほぼ空なら元音声にフォールバック）"""
    import librosa

    def p90_rms(path: str) -> float:
        y, _ = audio.load_audio(path)
        r = librosa.feature.rms(y=y)[0]
        return float(np.percentile(r, 90)) if len(r) else 0.0

    stem_rms, mix_rms = p90_rms(stem_wav), p90_rms(mix_wav)
    return mix_rms > 0 and stem_rms >= 0.02 * mix_rms


def _attach_frames(result: dict, raw_path: str, workdir: Path):
    """映像がある場合、各ノート/コードの開始時刻のフレームを切り出してリンクする

    どの弦を弾いているかはブリッジ側の映像から確認できるため、
    再生位置に連動したフレーム表示と、Claude Code の採譜磨き上げのために
    output/<id>/frames/ へ保存し、各イベントの "frame" にファイル名を入れる。
    （ミュートの有無はフレームだけでなく音声側の根拠でも確認する）
    """
    if not video.has_video(raw_path):
        return
    events = list(result.get("notes") or []) + list(result.get("chords") or [])
    if not events:
        return
    times = [float(e["start"]) for e in events]
    frames = video.extract_frames(raw_path, times, str(workdir / "frames"))
    if not frames:
        return
    linked = 0
    for e in events:
        name = video.frame_for(frames, float(e["start"]))
        if name:
            e["frame"] = name
            linked += 1
    if linked:
        result["meta"]["video_frames"] = len(frames)


def analyze(
    source: str,
    mode: str = "melody",
    chord_style: str = "chord",
    is_url: bool = False,
    title: str | None = None,
    keep_original: str | None = None,
    separate: bool = True,
):
    """
    解析の本体。
    mode: "melody"(単音/リード) | "chords"(コード/バッキング)
    chord_style: "chord"(フルコード) | "power"(パワーコード)  ※chordsモード時のみ
    keep_original: ブラウザ再生用に元ファイルを保持する場合のパス
    separate: Demucsによるギター音源分離を使う（未導入・失敗時は自動で元音声で解析）
    戻り値: 解析結果JSON(dict)。artifactsは output/<id>/ に保存。
    """
    if mode not in ("melody", "chords"):
        raise ValueError("mode は melody / chords のいずれかです")

    job_id = uuid.uuid4().hex[:8]
    workdir = OUTPUT_DIR / job_id
    workdir.mkdir(parents=True, exist_ok=True)

    if is_url:
        wav_path, dl_title, raw_path = audio.download_youtube(source, str(workdir))
        title = title or dl_title
    else:
        wav_path = audio.ensure_wav(source, str(workdir / "source.wav"))
        raw_path = source
        title = title or Path(source).stem

    # --- 音源分離（Demucs）: ギター成分が取れればそれを採譜に使う ---
    mix_wav = wav_path
    separated = False
    if separate:
        stem_path = sep.separate_guitar(raw_path, str(workdir))
        if stem_path:
            stem_mono = audio.ensure_wav(stem_path, str(workdir / "guitar_mono.wav"))
            if _is_usable_stem(stem_mono, mix_wav):
                wav_path = stem_mono
                separated = True

    y, sr = audio.load_audio(wav_path)  # 採譜用（分離時はギター成分）
    y_mix, _ = audio.load_audio(mix_wav)  # 拍・小節線検出用（原音）
    duration = float(len(y_mix) / sr)
    tempo, beats, barlines = _grid_times(y_mix, sr)

    result = {
        "meta": {
            "title": title,
            "duration": round(duration, 3),
            "tempo": round(tempo, 2),
            "mode": mode,
            "tuning": "EADGBE",
            "separated": separated,
            "source_job": job_id,
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
            # 音での確認: 見えている押さえ方のうち実際に鳴っていない弦（ミュート）を除去
            shape, muted = chords.filter_muted(y, sr, c["start"], c["end"], v["shape"])
            ev = {"start": c["start"], "end": c["end"], "label": c["label"], "shape": shape}
            if muted:
                ev["muted"] = muted
            result["chords"].append(ev)

    # 映像がある場合、各ノート/コード位置のフレームを切り出してリンクする
    _attach_frames(result, raw_path, workdir)

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
    # 磨き上げ元ジョブの映像フレームを引き継ぐ（リンク切れを防ぐ）
    src_job = data.get("meta", {}).get("source_job")
    if isinstance(src_job, str) and len(src_job) == 8:
        src_frames = OUTPUT_DIR / src_job / "frames"
        if src_frames.is_dir():
            shutil.copytree(src_frames, workdir / "frames", dirs_exist_ok=True)
    _save_artifacts(data, job_id, workdir)
    data["id"] = job_id
    return data


def _save_artifacts(result: dict, job_id: str, workdir: Path):
    (workdir / "analysis.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (workdir / "tab.txt").write_text(render.score_to_ascii(result), encoding="utf-8")
    pdf.render_pdf(result, str(workdir / "tab.pdf"))
