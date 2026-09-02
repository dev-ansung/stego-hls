import os
import subprocess
import sys
import threading
import time
from pathlib import Path


def prompt_input(prompt: str, default: str | None = None, required: bool = False) -> str:
    default_hint = f" [{default}]" if default else ""
    while True:
        try:
            val = input(f"{prompt}{default_hint}: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(0)

        # Handle dragged-and-dropped file paths with quotes or escaped spaces
        if (val.startswith("'") and val.endswith("'")) or (val.startswith('"') and val.endswith('"')):
            val = val[1:-1]
        val = val.replace("\\ ", " ")

        if not val and default:
            return default
        if not val and required:
            print("  ⚠️  This field is required.")
            continue
        return val


def run_interactive() -> None:
    print("\n" + "=" * 64)
    print("🎬  stego-hls Interactive Stream & Download Assistant")
    print("=" * 64 + "\n")

    # 1. URL
    url = prompt_input("1. Enter M3U8 Stream URL or Player Page URL", required=True)

    # 2. Referer
    default_ref = "supjav.com" if "supjav" in url or "fc2stream" in url or "turboviplay" in url else ""
    referer = prompt_input("2. Enter Referer (e.g. supjav.com, optional)", default=default_ref)

    # 3. SRT
    srt_input = prompt_input("3. Enter Subtitle .srt Path (Drag & drop file or press Enter to skip)", default=None)
    srt: str | None = None
    if srt_input:
        srt_path = Path(os.path.expanduser(srt_input))
        if not srt_path.exists():
            print(f"  ⚠️  Warning: File '{srt_path}' not found. Proceeding without subtitle.")
        else:
            srt = str(srt_path.resolve())

    # 4. Action Mode
    print("\nSelect Action:")
    print("  [1] 🌐 Live Stream in Web Browser (Video.js Player)")
    print("  [2] 🍎 Live Stream in Desktop Player (IINA)")
    print("  [3] 💾 Download / Clip Range to MP4")
    choice = prompt_input("\nChoose [1-3]", default="1")

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    if referer:
        ref = referer
        if not ref.startswith("http://") and not ref.startswith("https://"):
            ref = f"https://{ref}"
        headers["Referer"] = ref

    if choice in ("1", "2"):
        from stego_hls.server import HlsProxyServer

        port = 8000
        proxy = HlsProxyServer(
            url,
            headers=headers,
            srt_path=srt,
            port=port
        )

        stream_m3u8 = f"http://localhost:{port}/stream.m3u8"

        if choice == "2" and os.path.exists("/Applications/IINA.app"):
            cmd = ["/Applications/IINA.app/Contents/MacOS/iina-cli", stream_m3u8]
            if srt:
                cmd.append(f"--mpv-sub-files={srt}")

            def launch_iina():
                time.sleep(1.2)
                try:
                    subprocess.Popen(cmd)
                except Exception as e:
                    print(f"Could not launch IINA: {e}")

            threading.Thread(target=launch_iina, daemon=True).start()
            proxy.serve_forever(open_browser=False)
        else:
            proxy.serve_forever(open_browser=True)

    elif choice == "3":
        time_range = prompt_input("Enter Time Range (e.g. 08:00-12:00 or 1:30:00-1:45:00)", required=True)
        out_prefix = prompt_input("Enter Output Filename or Prefix", default="download_clip")
        from stego_hls.cli import run_batch

        task = {
            "url": url,
            "referer": referer,
            "output": out_prefix,
            "time": time_range,
            "srt": srt
        }
        run_batch([task], parallel=8, transcode=False, no_align=False, srt=srt)
