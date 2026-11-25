"""ギター音色モデル（学習）: 実機（テレキャス・レギュラーチューニング）の
全ポジションの「ギターの音」を学習し、検出ノートがギターの音かどうかを
判定する（無関係な音をタブ譜に出さないための音色フィルタ）。

学習（build_model）:
  6弦1フレット〜1弦22フレット（＋開放弦）の各 (弦, フレット) について、
  弦の種類（巻き線=暗い / プレーン=明るい）・フレット位置・
  ピッキングの明るさ違い（3バリアント）を倍音プロファイル（16倍音まで）として
  合成し、app/data/guitar_tone_model.npz に保存する。
  ギターの音は「倍音が整数倍に並ぶ」「アタックが速い（弾いた瞬間が最大）」
  「減衰する」「高次倍音ほど先に消える」という物理的な特徴を持つため、
  これでボーカル・パッド（持続音）・ノイズなどと区別できる。

判定（guitar_likelihood）:
  ノート区間のスペクトル（ビブラートに耐える帯域で測る）を学習済み辞書と
  照合し、0..1 の一致度（tone スコア）を返す。閾値による除去は
  web 側（web/server/core/pipeline.ts）が行う。
  判定に使える区間が短い/ほぼ無音の場合は 1.0 を返す（安全側）。
"""
from pathlib import Path

import numpy as np

from .tuning import MAX_FRET, TUNING_MIDI

DATA_DIR = Path(__file__).resolve().parent / "data"
MODEL_PATH = DATA_DIR / "guitar_tone_model.npz"

NHARM = 16                       # 学習する倍音の本数
VARIANTS = (0.75, 0.9, 1.05, 1.25, 1.5)  # ピッキングの明るさ違い（学習データの幅）
# パームミュート等の「減衰が速く高次倍音が少ない」音のバリアント
# （ミュートした実音は通常弾きより倍音が早く落ちる）
MUTE_VARIANTS = (0.45, 0.6, 0.72)
MUTE_P_EXTRA = 0.45              # ミュート時は倍音減衰指数をさらに深くする
# 歪み（ディストーション/ハムバッカー）の「倍音が豊かで減衰が遅い」音のバリアント
DIST_P_EXTRA = -0.22             # 歪みは偶数次・奇数次倍音が豊か（p が下がる）
MODEL_VERSION = 4

MIN_SEGMENT = 0.12               # これ未満のノートは判定材料不足として除去しない（秒）
MAX_SEGMENT = 0.6                # 判定に使う区間の上限（秒）
_RMS_FLOOR = 3e-3                # ほぼ無音として判定を保留するRMS

_cache: dict | None = None


# --- 学習: 全ポジションの倍音プロファイル辞書を作る ---

def _pickup_gain(f) -> np.ndarray:
    """テレキャス風シングルコイルの音色（周波数特性）。f は Hz（配列可）"""
    f = np.maximum(np.asarray(f, dtype=float), 1.0)
    g = np.ones_like(f)
    g *= 1.0 + 0.30 * np.exp(-((np.log2(f / 120.0)) ** 2) / 0.8)    # ボディ共振
    g *= 1.0 - 0.18 * np.exp(-((np.log2(f / 620.0)) ** 2) / 1.0)    # 中域のわずかな谷
    g *= 1.0 + 0.55 * np.exp(-((np.log2(f / 2800.0)) ** 2) / 0.7)   # プリゼンス峰
    g *= (1.0 + (f / 7000.0) ** 2) ** -0.35                         # 高域の緩やかな落ち
    return g


def _template_profile(f0: float, string_idx: int, fret: int, beta: float, mute: bool = False, dist: bool = False) -> np.ndarray:
    """1ポジションの倍音プロファイル（L2正規化）"""
    ks = np.arange(1, NHARM + 1, dtype=float)
    if string_idx <= 3:   # 6弦〜3弦: 巻き線（暗い）
        p = 1.28
    else:                 # 2弦・1弦: プレーン（明るい）
        p = 0.98
    p -= 0.006 * fret     # フレットが高いほど単弦が短く、やや明るい
    if mute:              # パームミュート等: 高次倍音がさらに早く落ちる
        p += MUTE_P_EXTRA
    if dist:              # 歪み/ハムバッカー: 倍音が豊か（減衰指数が浅い）
        p += DIST_P_EXTRA
    a = ks ** (-p) * (beta ** (ks - 1)) * _pickup_gain(ks * f0)
    return a / float(np.sqrt((a * a).sum()))


def build_model() -> dict:
    """6弦1F〜1弦22F（＋開放弦）を学習して辞書を保存する"""
    mids, strs, frets, harms = [], [], [], []
    for si, open_m in enumerate(TUNING_MIDI):  # index 0 = 6弦
        for fret in range(0, MAX_FRET + 1):
            midi = open_m + fret
            f0 = 440.0 * 2.0 ** ((midi - 69) / 12)
            for beta in VARIANTS:
                mids.append(midi)
                strs.append(6 - si)  # 表記は 6弦=6 / 1弦=1
                frets.append(fret)
                harms.append(_template_profile(f0, si, fret, beta))
            for beta in MUTE_VARIANTS:  # パームミュート等の減衰の速い音
                mids.append(midi)
                strs.append(6 - si)
                frets.append(fret)
                harms.append(_template_profile(f0, si, fret, beta, mute=True))
            for beta in (0.85, 1.15):  # 歪み/ハムバッカーの倍音が豊かな音
                mids.append(midi)
                strs.append(6 - si)
                frets.append(fret)
                harms.append(_template_profile(f0, si, fret, beta, dist=True))
    model = {
        "midi": np.array(mids, dtype=np.int32),
        "string": np.array(strs, dtype=np.int32),
        "fret": np.array(frets, dtype=np.int32),
        "harm": np.array(harms, dtype=np.float32),
        "version": np.array([MODEL_VERSION], dtype=np.int32),
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(MODEL_PATH, **model)
    return model


def load_model() -> dict:
    """学習済みモデルを読み込む（無ければ自動で学習する）"""
    global _cache
    if _cache is not None:
        return _cache
    if MODEL_PATH.exists():
        try:
            z = np.load(MODEL_PATH)
            if int(z["version"][0]) == MODEL_VERSION:
                _cache = {k: z[k] for k in ("midi", "string", "fret", "harm")}
                return _cache
        except Exception:
            pass
    _cache = build_model()
    return _cache


# --- 判定: ノート波形と学習済み辞書の照合 ---

def _obs_profile(seg: np.ndarray, sr: int, f0: float):
    """ノート区間の倍音プロファイルと、倍音間の余分なエネルギー比を測る

    ピーク探索はビブラート（±40セント程度）に耐える帯域で行う。
    """
    n_fft = 4096
    if len(seg) < n_fft:
        pad = np.pad(seg, (0, n_fft - len(seg)))
        specs = [np.abs(np.fft.rfft(pad * np.hanning(n_fft)))]
    else:
        specs = []
        for st in range(0, len(seg) - n_fft + 1, 1024):
            w = seg[st: st + n_fft] * np.hanning(n_fft)
            specs.append(np.abs(np.fft.rfft(w)))
            if len(specs) >= 5:
                break
    spec = np.mean(specs, axis=0)

    nyq = sr / 2.0
    k_max = min(NHARM, max(3, int(0.75 * nyq / f0)))
    bin_hz = sr / n_fft

    def band(f_c: float, w_hz: float) -> float:
        lo = max(1, int((f_c - w_hz) / bin_hz))
        hi = min(len(spec) - 1, int((f_c + w_hz) / bin_hz) + 1)
        if hi < lo:
            return 0.0
        return float(np.sqrt((spec[lo: hi + 1] ** 2).sum()))

    harm = []
    junk = []
    for k in range(1, k_max + 1):
        w_hz = max(2.5 * bin_hz, 0.022 * k * f0)  # ビブラートで広がっても拾う帯域
        harm.append(band(k * f0, w_hz))
        if k < 7:
            # 低次の倍音間のエネルギー（高次ほどビブラートで埋まるため判定に使わない）
            junk.append(band((k + 0.5) * f0, w_hz * 0.7))
    harm = np.asarray(harm, dtype=float)
    j = float(np.mean(junk)) if junk else 0.0
    junk_ratio = j / (float(np.mean(harm[: min(6, len(harm))])) + 1e-9)
    return harm, min(junk_ratio, 2.0)


def _env_scores(seg: np.ndarray, sr: int):
    """波形包絡からアタック・減衰のらしさを測る（戻り値: atk, dec 各0..1）

    ギターは「弾いた瞬間（先頭30ms）が最大」。歪みやコンプで減衰しない
    ロングトーン（サステイン）もギターとして扱い、減衰の重みは小さくする。
    ボーカル・パッドとの区別は主にアタックの速さで行う。
    """
    hop = max(1, int(0.01 * sr))
    n = max(1, len(seg) // hop)
    rms = np.array([
        float(np.sqrt(np.mean(seg[i * hop: (i + 1) * hop] ** 2))) for i in range(n)
    ])
    if n < 6 or float(rms.max()) <= 1e-9:
        return 1.0, 1.0
    i30 = max(1, int(0.03 * sr))
    i150 = max(i30 + 1, int(0.15 * sr))
    a0 = float(np.sqrt(np.mean(seg[:i30] ** 2)))
    a1 = float(np.sqrt(np.mean(seg[i30: min(i150, len(seg))] ** 2)))
    atk = float(np.clip((a0 / (a1 + 1e-9)) / 0.85, 0.25, 1.0))
    # 対数減衰率（区間全体の最小二乗フィット）
    i0 = max(1, int(0.10 * n))
    i1 = max(i0 + 3, int(0.92 * n))
    env = rms[i0:i1]
    if len(env) >= 4 and float(env.min()) > 0:
        tt = np.arange(i0, i1, dtype=float) * hop / sr
        slope = float(np.polyfit(tt, np.log(env), 1)[0])
    else:
        slope = -0.5
    # サステイン（slope≈0）でも0にならないようにする（歪みリードのロングトーン対策）
    dec = float(np.clip(-slope / 0.22, 0.0, 1.0))
    return atk, dec


def guitar_likelihood(y: np.ndarray, sr: int, midi: float,
                      t0: float | None = None, t1: float | None = None,
                      model: dict | None = None) -> float:
    """ノート区間がギターの音にどれだけ似ているか（0..1）

    データが足りない（短すぎる・ほぼ無音）場合は 1.0 を返して落とさない。
    学習範囲（レギュラー6弦開放〜1弦22F）外の音高は 0.4（ギターとして扱わない）。
    """
    if t0 is not None:
        i0 = max(0, int(float(t0) * sr))
        i1 = int(float(t1) * sr) if t1 is not None else i0 + int(MAX_SEGMENT * sr)
        seg = np.asarray(y[i0: min(i1, i0 + int(MAX_SEGMENT * sr))], dtype=float)
    else:
        seg = np.asarray(y[: int(MAX_SEGMENT * sr)], dtype=float)
    if len(seg) < int(MIN_SEGMENT * sr):
        return 1.0
    if float(np.sqrt(np.mean(seg ** 2))) < _RMS_FLOOR:
        return 1.0

    model = model or load_model()
    f0 = 440.0 * 2.0 ** ((float(midi) - 69.0) / 12.0)

    obs, junk_ratio = _obs_profile(seg, sr, f0)
    atk, dec = _env_scores(seg, sr)

    k = len(obs)
    # 平方根圧縮＋低次倍音の重み付き照合（ピッキング位置による明るさ差に頑健）
    w = 1.0 / np.sqrt(np.arange(1, k + 1, dtype=float))
    obs_c = np.sqrt(np.maximum(obs, 0.0)) * w
    obs_n = obs_c / (float(np.linalg.norm(obs_c)) + 1e-9)
    # 学習範囲外の音高（チョーキングで上がった音など）は、最も近い学習音高に
    # 寄せて照合する（音色が合えばギターとして扱う）
    all_midi = np.asarray(model["midi"], dtype=float)
    midi_c = min(max(float(midi), float(all_midi.min())), float(all_midi.max()))
    sims = []
    for i in np.nonzero(np.abs(all_midi - midi_c) <= 0.6)[0]:
        t = np.asarray(model["harm"][i][:k], dtype=float)
        t_c = np.sqrt(np.maximum(t, 0.0)) * w
        tn = t_c / (float(np.linalg.norm(t_c)) + 1e-9)
        sims.append(float(obs_n @ tn))
    if not sims:
        return 0.4  # 学習範囲外（レギュラーで弾けない音高）
    sim = max(sims)

    junk_score = float(np.clip(1.0 - 1.4 * junk_ratio, 0.0, 1.0))
    # アタックが速く倍音構造がギターらしい音は、減衰しないロングトーンでも
    # 減点しない（歪み・コンプで持続するリードのサステインを守る）。
    # ノイズ（倍音構造なし）やアタックの遅い持続音は従来どおり下げる
    if atk >= 0.7 and junk_score >= 0.5:
        dec = max(dec, 0.7)
    score = sim * (0.55 + 0.45 * atk) * (0.62 + 0.38 * junk_score) * (0.55 + 0.45 * dec)
    return float(np.clip(score, 0.0, 1.0))


if __name__ == "__main__":
    m = build_model()
    print(f"学習済みモデル: {MODEL_PATH}")
    print(f"  テンプレート数: {len(m['midi'])}")
    print(f"  音高範囲: MIDI {int(m['midi'].min())}〜{int(m['midi'].max())}（6弦1F〜1弦22F＋開放）")
