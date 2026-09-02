import http.server
import re
import urllib.parse
import webbrowser
from http import HTTPStatus
from pathlib import Path

import httpx

from stego_hls.cache import FileSegmentCache, SegmentCache
from stego_hls.decoders import BaseDecoder, StegoDecoder
from stego_hls.playlist import PlaylistParser, Timeline
from stego_hls.subtitles import srt_to_vtt

VIDEOJS_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>stego-hls Live Player</title>
  <link href="https://vjs.zencdn.net/8.10.0/video-js.css" rel="stylesheet" />
  <style>
    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }
    body {
      background-color: #0b0f19;
      color: #f8fafc;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      padding: 1rem;
    }
    .player-card {
      width: 100%;
      max-width: 1280px;
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.5);
    }
    .header {
      padding: 1rem 1.25rem;
      border-bottom: 1px solid #334155;
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: #0f172a;
    }
    .header h1 {
      font-size: 1.1rem;
      font-weight: 600;
      color: #38bdf8;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .header .tag {
      font-size: 0.75rem;
      padding: 0.2rem 0.6rem;
      background: #0284c7;
      color: #fff;
      border-radius: 9999px;
      font-weight: 600;
    }
    .video-wrapper {
      position: relative;
      width: 100%;
      aspect-ratio: 16 / 9;
      background: #000;
    }
    .video-js {
      width: 100% !important;
      height: 100% !important;
    }
    .vjs-default-skin .vjs-big-play-button {
      border-radius: 50% !important;
      width: 2.2em !important;
      height: 2.2em !important;
      line-height: 2.2em !important;
      margin-top: -1.1em !important;
      margin-left: -1.1em !important;
      border: none !important;
      background-color: rgba(2, 132, 199, 0.85) !important;
    }
    .footer {
      padding: 0.75rem 1.25rem;
      font-size: 0.82rem;
      color: #94a3b8;
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: #0f172a;
      border-top: 1px solid #334155;
    }
  </style>
</head>
<body>
  <div class="player-card">
    <div class="header">
      <h1>🎬 stego-hls Stream Player</h1>
      <span class="tag">Live On-the-Fly Decryption</span>
    </div>
    <div class="video-wrapper">
      <video id="stego-player" class="video-js vjs-default-skin vjs-big-play-centered" controls preload="auto">
        <source src="/stream.m3u8" type="application/x-mpegURL">
        __TRACK_TAG__
      </video>
    </div>
    <div class="footer">
      <span>Timeline Seeking & Subtitles Active</span>
      <span>HLS + Video.js</span>
    </div>
  </div>

  <script src="https://vjs.zencdn.net/8.10.0/video.min.js"></script>
  <script>
    const player = videojs('stego-player', {
      fluid: true,
      playbackRates: [0.5, 0.75, 1, 1.25, 1.5, 2],
      controlBar: {
        children: [
          'playToggle',
          'volumePanel',
          'currentTimeDisplay',
          'timeDivider',
          'durationDisplay',
          'progressControl',
          'liveDisplay',
          'remainingTimeDisplay',
          'customControlSpacer',
          'playbackRateMenuButton',
          'subsCapsButton',
          'fullscreenToggle'
        ]
      }
    });
  </script>
</body>
</html>
"""


class HlsStreamHandler(http.server.BaseHTTPRequestHandler):
    proxy_server: "HlsProxyServer"

    def do_GET(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path in ("/", "/index.html"):
            self.serve_player()
        elif path == "/stream.m3u8":
            self.serve_manifest()
        elif path.startswith("/segment/"):
            self.serve_segment(path)
        elif path == "/subtitles.vtt":
            self.serve_subtitles()
        elif path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def serve_player(self) -> None:
        track_tag = ""
        if self.proxy_server.srt_path:
            track_tag = '<track kind="subtitles" src="/subtitles.vtt" srclang="zh" label="Subtitles" default>'
        
        html = VIDEOJS_HTML_TEMPLATE.replace("__TRACK_TAG__", track_tag)
        data = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def serve_manifest(self) -> None:
        try:
            manifest_text = self.proxy_server.get_rewritten_manifest()
            data = manifest_text.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/vnd.apple.mpegurl")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Manifest fetch failed: {e}")

    def serve_segment(self, path: str) -> None:
        match = re.match(r"^/segment/(\d+)\.ts$", path)
        if not match:
            self.send_error(HTTPStatus.NOT_FOUND, "Invalid segment path")
            return

        seg_idx = int(match.group(1))
        try:
            ts_bytes = self.proxy_server.get_decoded_segment(seg_idx)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "video/mp2t")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(ts_bytes)))
            self.end_headers()
            self.wfile.write(ts_bytes)
        except Exception as e:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Segment decode failed: {e}")

    def serve_subtitles(self) -> None:
        if not self.proxy_server.srt_path:
            self.send_error(HTTPStatus.NOT_FOUND, "No subtitle file provided")
            return

        try:
            with open(self.proxy_server.srt_path, "r", encoding="utf-8", errors="ignore") as f:
                srt_content = f.read()
            vtt_content = srt_to_vtt(srt_content)
            data = vtt_content.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/vtt; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Subtitle error: {e}")

    def log_message(self, format: str, *args) -> None:
        # Suppress verbose standard HTTP request logging on segments
        if len(args) > 0 and isinstance(args[0], str) and "/segment/" in args[0]:
            return
        super().log_message(format, *args)


class HlsProxyServer:
    def __init__(
        self,
        master_url: str,
        *,
        headers: dict[str, str] | None = None,
        srt_path: str | Path | None = None,
        decoder: BaseDecoder | None = None,
        cache: SegmentCache | None = None,
        port: int = 8000
    ) -> None:
        self.master_url = master_url
        self.headers = headers or {}
        self.srt_path = Path(srt_path).resolve() if srt_path else None
        self.decoder = decoder or StegoDecoder()
        self.cache = cache or FileSegmentCache()
        self.port = port
        self.timeline: Timeline | None = None
        self.sub_playlist_url: str | None = None
        self.client = httpx.Client(follow_redirects=True, timeout=20.0)

    def resolve_timeline(self) -> None:
        """Fetches and parses the manifest to build the timeline segment map."""
        if self.timeline is not None:
            return

        resp = self.client.get(self.master_url, headers=self.headers if self.headers else None)
        resp.raise_for_status()
        master_text = resp.text

        if master_text.strip().lower().startswith("<!doctype") or "<html" in master_text.lower():
            embedded_urls = re.findall(r"['\"](https?://[^\'\"]+\.(?:m3u8|txt)[^\'\"]*)['\"]", master_text)
            if not embedded_urls:
                embedded_urls = re.findall(r"['\"]([^\'\"]+\.(?:m3u8|txt)[^\'\"]*)['\"]", master_text)
                embedded_urls = [urllib.parse.urljoin(self.master_url, u) for u in embedded_urls]
            if not embedded_urls:
                raise ValueError("No M3U8 streaming URLs found in player HTML.")
            self.sub_playlist_url = embedded_urls[0]
        else:
            self.sub_playlist_url = PlaylistParser.resolve_sub_playlist(master_text, master_url=self.master_url)

        sub_resp = self.client.get(self.sub_playlist_url, headers=self.headers if self.headers else None)
        sub_resp.raise_for_status()
        sub_text = sub_resp.text
        self.timeline = PlaylistParser.parse_manifest(sub_text, base_url=self.sub_playlist_url)

    def get_rewritten_manifest(self) -> str:
        """Generates an M3U8 playlist with segment URLs rewritten to local proxy paths."""
        self.resolve_timeline()
        assert self.timeline is not None

        target_dur = int(max((seg.duration for seg in self.timeline.segments), default=10) + 1)
        lines = [
            "#EXTM3U",
            "#EXT-X-VERSION:3",
            f"#EXT-X-TARGETDURATION:{target_dur}",
            "#EXT-X-MEDIA-SEQUENCE:0",
            "#EXT-X-PLAYLIST-TYPE:VOD"
        ]

        for seg in self.timeline.segments:
            lines.append(f"#EXTINF:{seg.duration:.6f},")
            lines.append(f"/segment/{seg.index}.ts")

        lines.append("#EXT-X-ENDLIST")
        return "\n".join(lines) + "\n"

    def get_decoded_segment(self, index: int) -> bytes:
        """Fetches a segment from CDN and decodes steganography in memory."""
        self.resolve_timeline()
        assert self.timeline is not None

        if index < 0 or index >= len(self.timeline.segments):
            raise IndexError(f"Segment index {index} out of range")

        seg = self.timeline.segments[index]
        
        req_headers = {}
        if "User-Agent" in self.headers:
            req_headers["User-Agent"] = self.headers["User-Agent"]
        if "Referer" in self.headers and "googleusercontent.com" not in seg.url:
            ref = self.headers["Referer"]
            if not ref.startswith("http://") and not ref.startswith("https://"):
                ref = f"https://{ref}"
            req_headers["Referer"] = ref
            parsed_ref = urllib.parse.urlparse(ref)
            req_headers["Origin"] = f"{parsed_ref.scheme}://{parsed_ref.netloc}"

        resp = self.client.get(seg.url, headers=req_headers if req_headers else None)
        resp.raise_for_status()
        raw_bytes = resp.content

        # Decode steganography (stripping mock PNG/JPEG header)
        return self.decoder.decode(raw_bytes)

    def serve_forever(self, open_browser: bool = True) -> None:
        """Starts the threading HTTP server and opens the web player."""
        handler_class = HlsStreamHandler
        handler_class.proxy_server = self

        server_address = ("", self.port)
        http.server.ThreadingHTTPServer.allow_reuse_address = True
        httpd = http.server.ThreadingHTTPServer(server_address, handler_class)
        web_url = f"http://localhost:{self.port}"
        stream_m3u8 = f"http://localhost:{self.port}/stream.m3u8"
        vtt_url = f"http://localhost:{self.port}/subtitles.vtt" if self.srt_path else None

        print("\n" + "=" * 64)
        print("🎬  stego-hls Live Stream Server Ready")
        print("=" * 64)
        print(f"🌐 Web Video Player:       {web_url}")
        print(f"📺 Raw Stream (IINA / VLC): {stream_m3u8}")
        if vtt_url:
            print(f"📝 Subtitles Track:        {vtt_url} ({self.srt_path.name})")
        if self.srt_path:
            print("\n💡 Desktop Player One-Liner (IINA):")
            print(f'   /Applications/IINA.app/Contents/MacOS/iina-cli "{stream_m3u8}" --mpv-sub-files="{self.srt_path}"')
        print("=" * 64)
        print("Press Ctrl+C to stop streaming.\n")

        if open_browser:
            webbrowser.open(web_url)

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[stego-hls] Shutting down live stream server...")
        finally:
            httpd.server_close()
            self.client.close()
