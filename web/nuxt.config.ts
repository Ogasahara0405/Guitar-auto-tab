// Nuxt 3 設定: UI + Nitroサーバー（API/採譜オーケストレーション）を1アプリで提供する。
// DSP（音声・映像の知覚）は Python ワーカー（../worker）を subprocess で呼ぶ。
export default defineNuxtConfig({
  compatibilityDate: "2025-01-01",
  ssr: false, // ローカルツールのためSPA（APIはNitroサーバーで処理）
  devtools: { enabled: false },
  typescript: { strict: true },
  css: ["~/assets/styles.css"],
  app: {
    head: {
      title: "Guitar Auto Tab",
      meta: [
        { name: "viewport", content: "width=device-width, initial-scale=1" },
      ],
    },
  },
  runtimeConfig: {
    // 既定は起動時のカレントディレクトリ（run.bat はリポジトリルートから起動する）
    gatRoot: "", // GAT_ROOT で上書き可（output/ と .venv の基準ディレクトリ）
    gatPython: "", // GAT_PYTHON で上書き可（worker 起動用 python）
  },
});
