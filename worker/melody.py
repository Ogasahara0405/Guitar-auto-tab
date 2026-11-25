"""メロディの採譜: 音声 → ノートイベント抽出（複数本指・同時発音に対応）

リードパートは単音だけでなく、ダブルストップ・オクターブ・
小コードなど複数本指で弾く部分がほとんどなので、
各セグメントで鳴っている音を最大3声まで検出する。
鳴っていない音（ミュート等）は倍音サリエンスが立たないため出力されない
（＝音での確認を優先し、映像だけでは見えないミュートを誤採譜しない）。
"""
import numpy as np
import librosa

# --- 多声音検出（ダブルストップ等）のパラメータ ---
_N_FFT = 4096
_HOP_MF = 512
_HARMONICS = 6          # サリエンスに使う倍音数
_MASK_HARMONICS = 10    # 主音判定後にマスクする倍音数
_PEAK_BINS = 2          # 倍音ピーク探索幅（±ビン）
_MASK_BINS = 5          # マスク幅（±ビン。ビブラート・ベンドで倍音が広がる分の余裕）
_CAND_MIDI0, _CAND_MIDI1, _CAND_STEP = 38.0, 88.0, 0.25
_SEC_MIN_RATIO = 0.30   # 副次音サリエンス / 主音サリエンス の下限
_SEC_NEAR_RATIO = 0.50  # 主音に近い副次音の下限（ビブラートの広がり対策）
_SEC_NEAR_ST = 2.5      # 「主音に近い」とみなす音程（半音）。3度（3半音）の同時発音は通常扱い
_SEC_MIN_SUPPORT = 2    # 副次音を支える倍音の最低本数
_SIM_SEC_IN_PRIM = 0.60  # 副次音が鳴っているフレームのうち主音も鳴っている割合
_SIM_PRIM_IN_SEC = 0.20  # 主音が鳴っているフレームのうち副次音も鳴っている割合
_SIM_LEVEL = 0.25       # 「鳴っている」判定のフレーム強度（2音の最大比に対する相対値）
_TRIM_LEVEL = 0.15      # ノート終端トリムの閾値（減衰音を切らなすぎない）
_MERGE_GAP = 0.04       # 同一音高の隣接ノートを結合するギャップ


def _nan_median_filter(x: np.ndarray, size: int = 5) -> np.ndarray:
    """NaNを無視する移動中央値フィルタ（ビブラート・ジッタ平滑化用）"""
    n = len(x)
    half = size // 2
    out = np.full(n, np.nan)
    for i in range(n):
        w = x[max(0, i - half): min(n, i + half + 1)]
        w = w[~np.isnan(w)]
        if len(w):
            out[i] = float(np.median(w))
    return out


# 量子化ヒステリシス（半音）。確定した音高から±この値以上動くまで遷移させない。
# チョーキング（1〜2半音のグライド）や深いビブラートで隣の半音をまたいでも、
# 音を細切れにしないための不感帯。
_HYST = 0.65
# これ以上連続的に動くピッチ移動をベンドとして記録する（半音）
_BEND_MIN = 0.8
# ビブラート判定（トレンド除去後の残差）
_VIB_STD = 0.15


def _hyst_quantize(x: np.ndarray) -> np.ndarray:
    """ヒステリシス付き半音量子化（細切れノートの防止）"""
    out = np.full(len(x), np.nan)
    cur = np.nan
    for i, v in enumerate(x):
        if np.isnan(v):
            continue
        if np.isnan(cur) or abs(v - cur) >= _HYST:
            cur = float(np.round(v))
        out[i] = cur
    return out


def _annotate_glide(seg: dict) -> None:
    """セグメント内のピッチ軌道から bend / vibrato 属性を推定して付与する。

    - bend: 開始ピッチからの単調な移動量（半音、0.5単位）。チョーキング/スライド
    - vibrato: 線形トレンド除去後に周期的な振動が残る場合
    """
    tr = seg.pop("track", None)
    if not tr or len(tr) < 4:
        return
    ts = np.array([p[0] for p in tr], dtype=float)
    ms = np.array([p[1] for p in tr], dtype=float)
    k = min(3, len(ms) // 2)
    drift = float(np.median(ms[-k:]) - np.median(ms[:k]))
    if abs(drift) >= _BEND_MIN:
        seg["bend"] = round(drift * 2.0) / 2.0
    if len(ms) >= 8:
        A = np.vstack([ts - ts.mean(), np.ones_like(ts)]).T
        coef, *_ = np.linalg.lstsq(A, ms, rcond=None)
        resid = ms - A @ coef
        if float(np.std(resid)) >= _VIB_STD and float(np.ptp(resid)) >= 2.5 * _VIB_STD:
            seg["vibrato"] = True


# ---- 多声音検出ユーティリティ（スペクトル上の倍音サリエンス） ----

def _build_cand_index(sr: int, n_fft: int):
    """候補MIDIグリッド → 倍音ピーク探索用のビンインデックス (C, H, 2*PEAK+1)"""
    mids = np.arange(_CAND_MIDI0, _CAND_MIDI1 + 1e-9, _CAND_STEP)
    freqs = 440.0 * 2.0 ** ((mids - 69.0) / 12.0)
    base = np.round(freqs * n_fft / sr).astype(int)  # (C,)
    ks = np.arange(1, _HARMONICS + 1)                # (H,)
    offs = np.arange(-_PEAK_BINS, _PEAK_BINS + 1)    # (P,)
    idx = base[:, None, None] * ks[None, :, None] + offs[None, None, :]
    idx = np.clip(idx, 1, n_fft // 2 - 1)
    return mids, idx


_HARM_W = 1.0 / np.arange(1, _HARMONICS + 1)  # 倍音の重み（低い倍音ほど重い）


def _salience(spectrum: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """スペクトルに対する倍音サリエンス
    idx が (C,H,P) なら全候補のサリエンス (C,)、(H,P) なら1音分のスカラー。
    """
    peaks = spectrum[idx].max(axis=-1)  # (..., H)
    return peaks @ _HARM_W


def _frame_salience(mags: np.ndarray, cand_idx_row: np.ndarray) -> np.ndarray:
    """1音のビン行に対するフレームごとのサリエンス (T,)"""
    peaks = mags[cand_idx_row].max(axis=1)  # (H, T)
    return _HARM_W @ peaks


def _peak(spectrum: np.ndarray, f: float, sr: int, n_fft: int) -> float:
    """スペクトルの f 付近のピーク強度"""
    b = int(round(f * n_fft / sr))
    lo, hi = max(1, b - _PEAK_BINS), min(len(spectrum) - 1, b + _PEAK_BINS)
    return float(spectrum[lo: hi + 1].max()) if hi >= lo else 0.0


def _mask_harmonics(spectrum: np.ndarray, f0: float, sr: int, n_fft: int):
    """f0 の倍音付近のビンをゼロにする（検出済み音の影響を除く）"""
    for k in range(1, _MASK_HARMONICS + 1):
        b = int(round(f0 * k * n_fft / sr))
        lo, hi = max(1, b - _MASK_BINS), min(len(spectrum) - 1, b + _MASK_BINS)
        spectrum[lo: hi + 1] = 0.0


def _support_count(spectrum: np.ndarray, f0: float, sr: int, n_fft: int, floor: float) -> int:
    """f0 を支える倍音の本数（ピークがスペクトル底面の3倍以上）"""
    n = 0
    for k in range(1, _HARMONICS + 1):
        if _peak(spectrum, f0 * k, sr, n_fft) >= 3.0 * floor:
            n += 1
    return n


def _octave_excess(spectrum: np.ndarray, f0: float, sr: int, n_fft: int) -> float:
    """f0 の1オクターブ上に独立した音が乗っているか（倍音の過剰で判定）

    2倍音の強度が幾何平均予測(√(a1*a3))を大きく超える、かつ
    4倍音も同様に過剰ならオクターブの同時発音とみなす。
    戻り値: 過剰比（1.0未満ならオクターブなし）
    """
    a = [_peak(spectrum, f0 * k, sr, n_fft) for k in range(1, 7)]
    if a[0] <= 1e-9:
        return 0.0
    pred2 = max((a[0] * a[2]) ** 0.5, 0.10 * a[0])
    pred4 = max((a[2] * a[4]) ** 0.5, 0.10 * a[2]) if a[2] > 1e-9 else 1e-9
    r2 = a[1] / pred2
    r4 = a[3] / pred4
    if r2 > 2.0 and r4 > 1.5:
        return min(1.0, 0.3 + 0.25 * (r2 - 2.0) + 0.25 * (r4 - 1.5))
    return 0.0


def _trim_span(env: np.ndarray, frame_times: np.ndarray, hop: float,
               lo_t: float, hi_t: float):
    """フレーム強度 env から有効区間 (start, end) を切り出す"""
    if env.size == 0:
        return None
    peak = float(env.max())
    if peak <= 0:
        return None
    c = int(np.argmax(env))
    thr = _TRIM_LEVEL * peak
    i0 = c
    while i0 > 0 and env[i0 - 1] >= thr:
        i0 -= 1
    i1 = c
    while i1 + 1 < env.size and env[i1 + 1] >= thr:
        i1 += 1
    start = max(lo_t, float(frame_times[i0]) - hop / 2)
    end = min(hi_t, float(frame_times[i1]) + hop / 2)
    if end - start < 0.05:
        return None
    return start, end


def extract_notes(y: np.ndarray, sr: int, hop_length: int = 256):
    """
    音声からノートイベント列を抽出する。
    戻り値: [{"start": 秒, "end": 秒, "midi": MIDIノート番号, "evidence": 0..1}, ...]
    同時発音（ダブルストップ等）は start が一致した複数ノートとして出力される。

    処理の流れ:
      1. pyin でF0追跡 → 中央値平滑化 → ヒステリシス付き半音量子化
         （チョーキング・深いビブラートで隣の半音をまたいでも音高を遷移させない）
      2. ピッチ連続性と無音ギャップでセグメント化。
         アタックを伴わない連続的なピッチ移動（ベンド/スライド/グリッサンド）は
         ノートを切らず、開始ノートの属性 bend / vibrato として記録する
      3. 極小セグメント・ほぼ無音のセグメント（残存ブリード等）を除去 →
         同一音高の隣接セグメントを継続ノートとして結合（アタック時の一時的なピッチ誤差対策）
      4. 強いオンセットでのみ同音の再ピッキングを分割
      5. 各セグメントで同時各セグメントで同時発音を検出（複数本指・ダブルストップ・オクターブ）。
         倍音サリエンスで候補を立て、フレーム単位の同時性（音での確認）で
         ビブラートの広がり・隣接ノートの漏れを誤検出しないようにする
      6. 同一音高の重なる/接するノート（分割・同時検出で細かくなったもの）を結合
    """
    if y.size == 0:
        return []

    f0, voiced, _ = librosa.pyin(
        y, fmin=70.0, fmax=1100.0, sr=sr, hop_length=hop_length
    )
    times = librosa.times_like(f0, sr=sr, hop_length=hop_length)
    frame_dur = hop_length / sr

    with np.errstate(divide="ignore", invalid="ignore"):
        midi = 69.0 + 12.0 * np.log2(f0 / 440.0)
    midi = np.where(np.isnan(midi), np.nan, midi)
    midi_s = _nan_median_filter(midi, size=5)
    midi_q = _hyst_quantize(midi_s)
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)
    if onset_env.shape[0] < midi_q.shape[0]:
        onset_env = np.pad(onset_env, (0, midi_q.shape[0] - onset_env.shape[0]))

    # --- Stage 1: セグメント化 ---
    gap_frames = max(1, int(round(0.06 / frame_dur)))
    raw = []
    cur = None
    gap = 0

    def close(end_t: float, reason: str):
        nonlocal cur
        if cur is not None:
            cur["end"] = float(end_t)
            cur["closed_by"] = reason
            raw.append(cur)
            cur = None

    def win_peak(arr, t_c, lo, hi):
        w = (times >= t_c + lo) & (times <= t_c + hi)
        return float(arr[w].max()) if w.any() else 0.0

    for i, t in enumerate(times):
        m = midi_q[i]
        if np.isnan(m):
            gap += 1
            if cur is not None and gap >= gap_frames:
                close(cur["last"] + frame_dur / 2, "gap")
            continue
        gap = 0
        if cur is None:
            cur = {
                "start": max(0.0, t - frame_dur / 2),
                "midi": int(m),
                "last": t,
                "last_raw": float(midi_s[i]),
                "track": [(float(t), float(midi_s[i]))],
                "atk": win_peak(onset_env, max(0.0, t - 0.05), -0.02, 0.10),
            }
        elif int(m) == cur["midi"]:
            cur["last"] = t
            cur["last_raw"] = float(midi_s[i])
            cur["track"].append((float(t), float(midi_s[i])))
        else:
            boundary = (cur["last"] + t) / 2
            # アタックを伴わず、ピッチが連続的に動く（ベンド/スライド）場合のみ
            # ノートを切らない。急な音程の切り替わり（新しい弾き出し）は分割する
            ref = cur["atk"] if cur["atk"] > 0 else float(np.median(onset_env)) + 1e-9
            smooth = abs(float(midi_s[i]) - cur.get("last_raw", float(midi_s[i]))) < 0.9
            if smooth and win_peak(onset_env, boundary, -0.05, 0.08) < 0.5 * ref:
                cur["last"] = t
                cur["last_raw"] = float(midi_s[i])
                cur["track"].append((float(t), float(midi_s[i])))
                continue
            close(boundary, "pitch")
            cur = {
                "start": boundary,
                "midi": int(m),
                "last": t,
                "last_raw": float(midi_s[i]),
                "track": [(float(t), float(midi_s[i]))],
                "atk": win_peak(onset_env, boundary, -0.02, 0.10),
            }
    if cur is not None:
        close(cur["last"] + frame_dur / 2, "end")

    # --- Stage 2: 極小セグメント（アタック瞬間の誤検出）と
    #     ほぼ無音のセグメント（残存ブリード・ノイズの誤検出）を除去 ---
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    rms_times = librosa.times_like(rms, sr=sr, hop_length=hop_length)
    # フロアは曲中の最大音量（p90）基準で低めに: サビの大きいフレーズに
    # 釣られて、控えめなメロディや減衰途中の音が消えないようにする
    energy_floor = 0.02 * float(np.percentile(rms, 90)) if len(rms) else 0.0

    def seg_peak_rms(t0: float, t1: float) -> float:
        m = (rms_times >= t0) & (rms_times < t1)
        return float(rms[m].max()) if m.any() else 0.0

    kept = [
        s for s in raw
        if s["end"] - s["start"] >= 0.04
        and seg_peak_rms(s["start"], s["end"]) >= energy_floor
    ]

    # --- Stage 3: 同一音高の隣接セグメント結合 ---
    # ピッチ誤差で分断された継続ノートのみ結合し、
    # 無音ギャップで切れた同音の連打はノートを分離したまま維持する
    merged = []
    for seg in kept:
        if merged and seg["midi"] == merged[-1]["midi"] and merged[-1]["closed_by"] != "gap":
            merged[-1]["end"] = seg["end"]
            merged[-1]["closed_by"] = seg["closed_by"]
            merged[-1]["track"] = merged[-1].get("track", []) + seg.get("track", [])
        else:
            merged.append(dict(seg))

    # ベンド/ビブラートをノート属性として記録（ピッチの連続移動で音を切らないため）
    for seg in merged:
        _annotate_glide(seg)

    # --- Stage 4: 再ピッキング分割（同音の連打） ---
    # オンセット位置に加えて「エネルギーの深い落ち込み（ディップ）」か
    # 「強いピッキングのアタック（スペクトルフラックス）」がある場合に分割する。
    # 歪み（コンプレッション）でディップが浅い同音連打も、アタックの立ち上がりで
    # 検出できるようにする。
    onsets = librosa.onset.onset_detect(
        y=y, sr=sr, hop_length=hop_length, units="time",
        backtrack=True, delta=0.2, wait=int(0.1 / frame_dur),
    )

    def rms_max(t0: float, t1: float) -> float:
        m = (rms_times >= t0) & (rms_times < t1)
        return float(rms[m].max()) if m.any() else 0.0

    out = []
    for seg in merged:
        dur = seg["end"] - seg["start"]
        splits = []
        if dur >= 0.12:
            for o in onsets:
                if not (seg["start"] + 0.1 < o < seg["end"] - 0.1):
                    continue
                # 分割点はその付近のRMS最小点
                w0, w1 = max(seg["start"], o - 0.05), min(seg["end"], o + 0.08)
                m = (rms_times >= w0) & (rms_times < w1)
                if not m.any():
                    continue
                idx = int(np.argmin(rms[m]))
                dip_t = float(rms_times[m][idx])
                r_dip = float(rms[m][idx])
                r_prev = rms_max(dip_t - 0.25, dip_t - 0.05)
                r_next = rms_max(dip_t + 0.02, dip_t + 0.15)
                deep_dip = r_dip < 0.5 * r_prev and r_dip < 0.5 * r_next
                # ピッキングのアタック（スペクトルフラックス）がセグメント開始時と
                # 同程度に立っていれば、浅いディップでも再ピッキングとみなす
                strong = win_peak(onset_env, o, -0.04, 0.06) >= 0.8 * max(
                    seg.get("atk") or 0.0, 1e-9
                )
                if not (deep_dip or strong):
                    continue
                if dip_t - seg["start"] >= 0.08 and seg["end"] - dip_t >= 0.08:
                    splits.append(dip_t if deep_dip else float(o))
        if splits:
            pts = [seg["start"]] + sorted(splits) + [seg["end"]]
            for a, b in zip(pts[:-1], pts[1:]):
                if b - a >= 0.06:
                    item = {"start": float(a), "end": float(b), "midi": seg["midi"]}
                    for k in ("bend", "vibrato"):
                        if k in seg:
                            item[k] = seg[k]
                    out.append(item)
        else:
            item = {"start": float(seg["start"]), "end": float(seg["end"]), "midi": seg["midi"]}
            for k in ("bend", "vibrato"):
                if k in seg:
                    item[k] = seg[k]
            out.append(item)

    if not out:
        return []

    # --- Stage 5: 同時発音の検出（複数本指・ダブルストップ・オクターブ） ---
    mags = np.abs(librosa.stft(y, n_fft=_N_FFT, hop_length=_HOP_MF))
    mf_times = librosa.frames_to_time(np.arange(mags.shape[1]), sr=sr, hop_length=_HOP_MF)
    mf_hop = _HOP_MF / sr
    cand_mids, cand_idx = _build_cand_index(sr, _N_FFT)
    spec_floor = float(np.median(mags)) + 1e-9

    def seg_frames(t0: float, t1: float) -> np.ndarray:
        return np.where((mf_times >= t0) & (mf_times < t1))[0]

    def is_simultaneous(f_a: float, f_b: float, frames: np.ndarray) -> bool:
        """フレーム単位で2音が同時に鳴っているか（音での確認）"""
        if frames.size == 0:
            return False
        fa = _frame_salience(mags[:, frames], cand_idx_row_for(f_a))
        fb = _frame_salience(mags[:, frames], cand_idx_row_for(f_b))
        # 「鳴っている」判定は2音の最大強度に対する相対値で行う
        # （各音の自己最大比だと、ビブラートの広がりで生じる弱い候補が
        #   全フレーム「鳴っている」と誤判定しやすいため）
        ref = max(float(fa.max()), float(fb.max()), 1e-12)
        act_a = fa >= _SIM_LEVEL * ref
        act_b = fb >= _SIM_LEVEL * ref
        both = act_a & act_b
        need = 2 if frames.size >= 4 else 1
        if int(both.sum()) < need:
            return False
        if act_b.sum() and both.sum() / act_b.sum() < _SIM_SEC_IN_PRIM:
            return False
        if act_a.sum() and both.sum() / act_a.sum() < _SIM_PRIM_IN_SEC:
            return False
        return True

    def cand_idx_row_for(f: float) -> np.ndarray:
        """任意周波数の倍音ピークビン行 (H, P)"""
        b = int(round(f * _N_FFT / sr))
        ks = np.arange(1, _HARMONICS + 1)
        offs = np.arange(-_PEAK_BINS, _PEAK_BINS + 1)
        idx = b * ks[:, None] + offs[None, :]
        return np.clip(idx, 1, _N_FFT // 2 - 1)

    def add_secondary(notes, seg, f_sec, ratio):
        frames = seg_frames(seg["start"], seg["end"])
        if frames.size == 0:
            return
        f_prim = 440.0 * 2.0 ** ((seg["midi"] - 69.0) / 12.0)
        if abs(f_sec - f_prim) / max(f_prim, 1e-9) < 0.04:
            return  # 主音とほぼ同じ
        # 主音に近い副次音はビブラートの広がりの疑いが強い → 強い根拠のみ採用
        if abs(12.0 * np.log2(f_sec / max(f_prim, 1e-9))) < _SEC_NEAR_ST and ratio < _SEC_NEAR_RATIO:
            return
        if not is_simultaneous(f_prim, f_sec, frames):
            return
        env = _frame_salience(mags[:, frames], cand_idx_row_for(f_sec))
        span = _trim_span(env, mf_times[frames], mf_hop, seg["start"], seg["end"])
        if span is None:
            return
        midi_sec = int(round(69.0 + 12.0 * np.log2(f_sec / 440.0)))
        if midi_sec == seg["midi"]:
            return
        notes.append({
            "start": round(span[0], 3),
            "end": round(span[1], 3),
            "midi": midi_sec,
            "evidence": round(float(min(1.0, max(0.0, ratio))), 3),
            "sec": True,
        })

    notes = []
    for seg in out:
        frames = seg_frames(seg["start"], seg["end"])
        if frames.size == 0:
            notes.append({**seg, "evidence": 1.0, "sec": False})
            continue
        S_seg = np.median(mags[:, frames], axis=1)
        f_prim = 440.0 * 2.0 ** ((seg["midi"] - 69.0) / 12.0)

        # 基音がほぼ無いセグメント = 複数音の共通周期をpyinが誤検出している
        # （例: 3度・4度のダブルストップで、2音の最小公倍音の低い音を拾う）。
        # スペクトルから鳴っている音を直接検出する。
        amps = [_peak(S_seg, f_prim * k, sr, _N_FFT) for k in range(1, 7)]
        if amps[0] < 0.25 * max(amps[1:]) and not seg.get("bend"):
            S_work = S_seg.copy()
            ref = 0.0
            picked = []
            attempts = 0
            while len(picked) < 3 and attempts < 5:
                attempts += 1
                sal = _salience(S_work, cand_idx)
                k_best = int(np.argmax(sal))
                s_best = float(sal[k_best])
                if not ref:
                    if s_best <= 0:
                        break
                    ref = s_best
                elif s_best < _SEC_MIN_RATIO * ref:
                    break
                f_v = 440.0 * 2.0 ** ((cand_mids[k_best] - 69.0) / 12.0)
                if _support_count(S_work, f_v, sr, _N_FFT, spec_floor) < _SEC_MIN_SUPPORT:
                    break
                ratio = s_best / ref
                # 検出済み音の近傍候補はビブラートの広がりの疑い → 強い根拠のみ採用
                near = any(
                    abs(12.0 * np.log2(f_v / max(fp, 1e-9))) < _SEC_NEAR_ST for fp in picked
                )
                if near and ratio < _SEC_NEAR_RATIO:
                    _mask_harmonics(S_work, f_v, sr, _N_FFT)
                    continue
                env = _frame_salience(mags[:, frames], cand_idx_row_for(f_v))
                span = _trim_span(env, mf_times[frames], mf_hop, seg["start"], seg["end"])
                _mask_harmonics(S_work, f_v, sr, _N_FFT)
                if span is None:
                    continue
                # 音での確認: フレーム単位で同時に鳴っている声だけ採用
                if picked and not is_simultaneous(picked[0], f_v, frames):
                    continue
                picked.append(f_v)
                notes.append({
                    "start": round(span[0], 3),
                    "end": round(span[1], 3),
                    "midi": int(round(69.0 + 12.0 * np.log2(f_v / 440.0))),
                    "evidence": round(min(1.0, ratio), 3),
                    "sec": True,
                })
            continue

        sal_prim = _salience(S_seg, cand_idx_row_for(f_prim))
        notes.append({**seg, "evidence": 1.0, "sec": False})

        # ベンド/スライド中のセグメントは倍音が動いてリーク（誤った副次声）を
        # 引き起こしやすいため、副次声の検出を行わない
        if seg.get("bend"):
            continue

        # マスク法で副次音を最大2つまで検出
        S_work = S_seg.copy()
        _mask_harmonics(S_work, f_prim, sr, _N_FFT)
        found = []
        attempts = 0
        while len(found) < 2 and attempts < 4:
            attempts += 1
            peaks = S_work[cand_idx].max(axis=2)  # (C, H)
            sal = peaks @ _HARM_W
            k_best = int(np.argmax(sal))
            ratio = float(sal[k_best] / sal_prim) if sal_prim > 0 else 0.0
            if ratio < _SEC_MIN_RATIO:
                break
            f_sec = 440.0 * 2.0 ** ((cand_mids[k_best] - 69.0) / 12.0)
            if _support_count(S_work, f_sec, sr, _N_FFT, spec_floor) < _SEC_MIN_SUPPORT:
                # サリエンスは立つが倍音の裏付けがない → そこで打ち切り
                break
            dup = any(abs(f_sec - f) / f < 0.04 for f in found)
            near = abs(12.0 * np.log2(f_sec / max(f_prim, 1e-9))) < _SEC_NEAR_ST
            if dup or (near and ratio < _SEC_NEAR_RATIO):
                # 主音・検出済み音の近傍候補はビブラートの広がりの疑い →
                # マスクして次に強い候補を探す
                _mask_harmonics(S_work, f_sec, sr, _N_FFT)
                continue
            found.append(f_sec)
            add_secondary(notes, seg, f_sec, ratio)
            _mask_harmonics(S_work, f_sec, sr, _N_FFT)

        # オクターブの同時発音（例: オクターブ奏法）を倍音の過剰で検出
        if len(found) < 2:
            excess = _octave_excess(S_seg, f_prim, sr, _N_FFT)
            if excess > 0:
                add_secondary(notes, seg, f_prim * 2.0, max(0.3, excess))

    # --- Stage 6: 同一音高の重なる/接するノートを結合 ---
    # 同時検出・pyinの振動で細かく分かれた同じ音を1ノートに戻す。
    # Stage 4の再ピッキング分割（主音どうしの接続）は保持するため、
    # 副次音を含む結合のみ行う。同時発音では2音が交互に並ぶため、
    # 直前だけでなく同一音高の未結合ノート全体と突き合わせる。
    notes.sort(key=lambda n: (n["start"], n["midi"], not n["sec"]))
    combined = []
    for n in notes:
        hit = None
        for p in reversed(combined):
            if p["midi"] == n["midi"] and n["start"] <= p["end"] + _MERGE_GAP:
                hit = p
                break
        if hit is not None and (hit["sec"] or n["sec"]):
            hit["end"] = max(hit["end"], n["end"])
            hit["evidence"] = max(hit["evidence"], n["evidence"])
            hit["sec"] = True
        else:
            combined.append(dict(n))

    result = []
    for n in combined:
        item = {
            "start": round(float(n["start"]), 3),
            "end": round(float(n["end"]), 3),
            "midi": int(n["midi"]),
            "evidence": float(n.get("evidence", 1.0)),
        }
        if n.get("bend"):
            item["bend"] = round(float(n["bend"]), 2)   # チョーキング/スライド（半音）
        if n.get("vibrato"):
            item["vibrato"] = True
        result.append(item)
    return result
