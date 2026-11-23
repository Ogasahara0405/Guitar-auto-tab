"""採譜ワーカーCLI: web（TypeScript）から subprocess で呼ばれ、JSON を返す

コマンド:
  acquire      --url <url> | --file <path> --out <dir>
      YouTube/ローカル媒体を取得し、{wav, title, media} を返す
  perceive     --src <media> --out <dir> --mode melody|chords [--no-separate]
      音声・映像の知覚結果（notes/chords/play/beats など）を JSON で返す
  frames       --src <media> --out <dir> --times <json>
      指定時刻の映像フレームを切り出し、{時刻: ファイル名} を返す
  verify-mutes --audio <wav> --request <json>
      押さえ方の各弦が実際に鳴っているかを音声で確認し、{muted: [[弦], ...]} を返す

いずれも結果は stdout へ1行の JSON（NaN/Inf は null に正規化）。
"""
import argparse
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np

from . import audio, chords, melody, sep, tone, video

# CLI契約: 結果JSONはこのマーカーの後ろに1行で出力する（ノイズ耐性のため）
JSON_MARKER = "__GAT_JSON__"

# コンソールの既定エンコード（Windowsのcp932等）に依存しないよう、
# stdout/stderr を UTF-8 に固定する（タイトルの μ 等の文字で落ちないため）
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _dump(obj) -> None:
    """NaN/Inf を含まない安全な JSON を stdout へ出力する

    他の出力（yt-dlp の進捗など）が改行なしで混ざっても壊れないよう、
    専用マーカー行の後ろに JSON を1行で置いて flush する。
    （クライアントは最後のマーカー以降を JSON として読む）
    """

    def clean(o):
        if isinstance(o, float):
            return o if math.isfinite(o) else None
        if isinstance(o, dict):
            return {str(k): clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [clean(v) for v in o]
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            v = float(o)
            return v if math.isfinite(v) else None
        return o

    # コンソールエンコードに依存しないようバイト列で直接書く（μ 等の文字対策）
    payload = ("\n" + JSON_MARKER + json.dumps(clean(obj), ensure_ascii=False) + "\n").encode("utf-8")
    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.flush()


def _read_request(path: str):
    """--request/--times に渡すJSONを読む（"-" なら stdin）"""
    if path == "-":
        return json.loads(sys.stdin.read())
    return json.loads(Path(path).read_text(encoding="utf-8"))


def cmd_acquire(args) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.url:
        wav, title, media = audio.download_youtube(args.url, str(out))
        _dump({"wav": Path(wav).name, "title": title, "media": Path(media).name})
        return
    src = Path(args.file)
    ext = src.suffix or ".bin"
    media_name = f"source_original{ext}"
    shutil.copyfile(src, out / media_name)
    wav = audio.ensure_wav(str(src), str(out / "source.wav"))
    _dump({"wav": Path(wav).name, "title": src.stem, "media": media_name})


def _grid_times(y: np.ndarray, sr: int):
    """表示グリッド用のテンポ・ビート・小節線を計算"""
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


def cmd_perceive(args) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    src = args.src

    # --- 音源分離（Demucs）: ギター成分が取れればそれを採譜に使う ---
    mix_wav = audio.ensure_wav(src, str(out / "mix.wav"))
    wav_path = mix_wav
    separated = False
    if not args.no_separate:
        stem_path = sep.separate_guitar(src, str(out))
        if stem_path:
            stem_mono = audio.ensure_wav(stem_path, str(out / "guitar_mono.wav"))
            if _is_usable_stem(stem_mono, mix_wav):
                wav_path = stem_mono
                separated = True

    y, sr = audio.load_audio(wav_path)   # 採譜用（分離時はギター成分）
    y_mix, _ = audio.load_audio(mix_wav)  # 拍・小節線検出用（原音）
    duration = float(len(y_mix) / sr)
    tempo, beats, barlines = _grid_times(y_mix, sr)

    # --- 映像を主・音声を従: 映像の演奏動作を先に解析しておく ---
    # ノートの選別（ゲート）は web 側がこの play データで行う
    play = video.analyze_play(src)

    notes = []
    chords_out = []
    chords_tempo = None
    if args.mode == "melody":
        model = tone.load_model()
        for n in melody.extract_notes(y, sr):
            s = tone.guitar_likelihood(
                y, sr, n["midi"], t0=n.get("start"), t1=n.get("end"), model=model
            )
            notes.append({**n, "tone": round(float(s), 3)})
    else:
        ch = chords.extract_chords(y, sr)
        chords_out = ch["chords"]
        chords_tempo = round(ch["tempo"], 2)

    _dump(
        {
            "duration": round(duration, 3),
            "tempo": round(tempo, 2),
            "chords_tempo": chords_tempo,
            "separated": separated,
            "mode": args.mode,
            "audio_file": Path(wav_path).name,
            "notes": notes,
            "chords": chords_out,
            "play": play,
            "beats": beats,
            "barlines": barlines,
        }
    )


def cmd_frames(args) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    times = _read_request(args.times)
    frames = video.extract_frames(src=args.src, times=times, outdir=str(out / "frames"))
    _dump({"frames": frames})


def cmd_verify_mutes(args) -> None:
    req = _read_request(args.request)
    y, sr = audio.load_audio(args.audio)
    muted = []
    for ev in req:
        shape = [
            {"string": int(s["string"]), "fret": int(s["fret"])}
            for s in (ev.get("shape") or [])
        ]
        _kept, m = chords.filter_muted(y, sr, float(ev["start"]), float(ev["end"]), shape)
        muted.append(sorted(int(x) for x in m))
    _dump({"muted": muted})


def main() -> None:
    p = argparse.ArgumentParser(prog="worker", description="採譜ワーカー（DSP知覚層）")
    sub = p.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("acquire", help="YouTube/ローカル媒体の取得")
    g = pa.add_mutually_exclusive_group(required=True)
    g.add_argument("--url")
    g.add_argument("--file")
    pa.add_argument("--out", required=True)

    pp = sub.add_parser("perceive", help="音声・映像の知覚結果をJSONで返す")
    pp.add_argument("--src", required=True)
    pp.add_argument("--out", required=True)
    pp.add_argument("--mode", choices=("melody", "chords"), required=True)
    pp.add_argument("--no-separate", action="store_true")

    pf = sub.add_parser("frames", help="指定時刻の映像フレームを切り出す")
    pf.add_argument("--src", required=True)
    pf.add_argument("--out", required=True)
    pf.add_argument("--times", required=True, help='JSON配列（"-" で stdin）')

    pm = sub.add_parser("verify-mutes", help="押さえ方の鳴っていない弦を音声で確認")
    pm.add_argument("--audio", required=True)
    pm.add_argument("--request", required=True, help='JSON（"-" で stdin）')

    args = p.parse_args()
    {
        "acquire": cmd_acquire,
        "perceive": cmd_perceive,
        "frames": cmd_frames,
        "verify-mutes": cmd_verify_mutes,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
