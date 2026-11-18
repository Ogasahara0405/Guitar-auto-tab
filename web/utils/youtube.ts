/** YouTube IFrame API のローダーと最小限の型 */

export interface YTPlayer {
  getCurrentTime(): number;
  destroy(): void;
}

interface YTPlayerOptions {
  videoId: string;
  playerVars?: Record<string, number | string>;
  events?: { onReady?: () => void };
}

interface YTNamespace {
  Player: new (element: HTMLElement, options: YTPlayerOptions) => YTPlayer;
}

declare global {
  interface Window {
    YT?: YTNamespace;
    onYouTubeIframeAPIReady?: () => void;
  }
}

let apiPromise: Promise<void> | null = null;

export function loadYouTubeAPI(): Promise<void> {
  if (window.YT?.Player) return Promise.resolve();
  if (!apiPromise) {
    apiPromise = new Promise((resolve) => {
      const prev = window.onYouTubeIframeAPIReady;
      window.onYouTubeIframeAPIReady = () => {
        prev?.();
        resolve();
      };
      const s = document.createElement("script");
      s.src = "https://www.youtube.com/iframe_api";
      document.head.appendChild(s);
    });
  }
  return apiPromise;
}

export function extractYouTubeId(url: string): string | null {
  const m = url.match(/(?:youtu\.be\/|[?&]v=|shorts\/|embed\/)([A-Za-z0-9_-]{11})/);
  return m ? m[1] : null;
}

export function createYTPlayer(
  mount: HTMLElement,
  videoId: string,
  onReady: () => void
): YTPlayer {
  const YT = window.YT;
  if (!YT?.Player) throw new Error("YouTube API が読み込まれていません");
  return new YT.Player(mount, {
    videoId,
    playerVars: { rel: 0 },
    events: { onReady },
  });
}
