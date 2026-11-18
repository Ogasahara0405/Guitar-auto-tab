"""採譜ワーカー（DSP知覚層）

librosa / numpy / Demucs に依存する音声・映像の知覚処理を担う。
決定ロジック（弦/フレット割当・ボイシング・映像ゲート・譜面描画）は
web/（TypeScript）側が担当し、このパッケージは CLI（__main__.py）経由で
JSON を渡して呼ばれる（python -m worker acquire|perceive|frames|verify-mutes）。
"""
