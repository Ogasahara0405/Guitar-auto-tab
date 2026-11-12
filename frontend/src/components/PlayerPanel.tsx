import { useEffect, useRef } from "react";
import type { AnalysisResult } from "../types";
import { mediaUrl } from "../api";
import { createYTPlayer, extractYouTubeId, loadYouTubeAPI } from "../lib/youtube";
import type { YTPlayer } from "../lib/youtube";
import type { TimeSource } from "../App";

interface Props {
  result: AnalysisResult;
  /** YouTube URL（空なら result のメディアファイルを再生） */
  sourceUrl: string;
  timeSource: TimeSource;
}

type Kind = "youtube" | "video" | "audio" | "none";

function isVideoFile(name: string): boolean {
  return /\.(mp4|webm|mkv|mov|avi|m4v)$/i.test(name);
}

function detectKind(result: AnalysisResult, sourceUrl: string): Kind {
  if (sourceUrl) return extractYouTubeId(sourceUrl) ? "youtube" : "none";
  const mf = result.meta.media_file;
  if (!mf) return "none";
  return isVideoFile(mf) ? "video" : "audio";
}

export default function PlayerPanel({ result, sourceUrl, timeSource }: Props) {
  const ytHostRef = useRef<HTMLDivElement | null>(null);
  const mediaRef = useRef<HTMLVideoElement | HTMLAudioElement | null>(null);
  const playerRef = useRef<YTPlayer | null>(null);

  const kind = detectKind(result, sourceUrl);
  const src = mediaUrl(result.id);

  useEffect(() => {
    if (kind === "none") {
      timeSource.current = () => 0;
      return;
    }

    if (kind === "youtube") {
      let cancelled = false;
      timeSource.current = () => 0;
      const videoId = extractYouTubeId(sourceUrl);
      if (!videoId) return;
      loadYouTubeAPI().then(() => {
        if (cancelled || !ytHostRef.current || !videoId) return;
        const host = ytHostRef.current;
        host.innerHTML = "";
        const mount = document.createElement("div");
        host.appendChild(mount);
        const player = createYTPlayer(mount, videoId, () => {
          timeSource.current = () => {
            try {
              return player.getCurrentTime() || 0;
            } catch {
              return 0;
            }
          };
        });
        playerRef.current = player;
      });
      return () => {
        cancelled = true;
        timeSource.current = () => 0;
        try {
          playerRef.current?.destroy();
        } catch {
          /* プレイヤー未初期化 */
        }
        playerRef.current = null;
        if (ytHostRef.current) ytHostRef.current.innerHTML = "";
      };
    }

    // <video> / <audio> によるローカルメディア再生
    timeSource.current = () => (mediaRef.current?.currentTime ?? 0) || 0;
    return () => {
      timeSource.current = () => 0;
    };
  }, [kind, sourceUrl, result.id, timeSource]);

  if (kind === "none") return null;

  return (
    <div className="player-wrap">
      {kind === "youtube" && <div ref={ytHostRef} />}
      {kind === "video" && (
        <video
          ref={(el) => {
            mediaRef.current = el;
          }}
          controls
          playsInline
          src={src}
        />
      )}
      {kind === "audio" && (
        <audio
          ref={(el) => {
            mediaRef.current = el;
          }}
          controls
          src={src}
        />
      )}
    </div>
  );
}
