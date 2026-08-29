# stego-hls (m3u8-downloader)

A high-performance, steganography-aware HLS/M3U8 downloader and clipper. `stego-hls` automatically parses HLS playlists, downloads only the segments required for your target ranges, extracts video payloads hidden inside mock image files (PNG/JPEG/GIF), and losslessly outputs clipped MP4 files.

---

## Features
*   **Intelligent Timeline Mapping:** Download only the specific HLS segments required for target timestamp ranges, saving massive amounts of bandwidth and time.
*   **Steganographic Extraction:** Scans trailing image payloads to locate standard MPEG Transport Stream sync patterns, stripping away mock headers dynamically.
*   **Zero-Temp-File Piping:** Pipes concatenated Transport Stream packets directly into `ffmpeg`'s `stdin` (pipe) to avoid redundant disk writes and extend SSD/HDD lifespan.
*   **Lossless Stream Copying:** Uses `-c copy` by default for sub-second, quality-retaining clipping and remuxing.
*   **Extensible Decoder Hook:** Easily register custom decoders (e.g., XOR ciphers, AES-128, or proprietary headers).

---

## Installation

### Prerequisites
*   Python 3.12+ (modern Python standards)
*   `ffmpeg` installed on your system path.

### Zero-Install Remote Execution (via `uvx`)
You can run this CLI tool directly from the repository without cloning or manual installation:
```bash
uvx --from git+https://github.com/dev-ansung/stego-hls.git stego-hls <URL> [OPTIONS]
```

### Local Development Usage (via `uv`)
If you have cloned the repository locally, run the executable script directly:
```bash
uv run m3u8_downloader.py <URL> [OPTIONS]
```

---

## CLI Usage

### Direct Command Options
*   `URL` (Positional): The HLS manifest M3U8 link or HTML player page.
*   `-t, --time <RANGE>`: Target timing range (e.g., `08:00-12:00` or `2:18:00`). Can be specified multiple times to extract multiple clips.
*   `-r, --referer <URL>`: Optional Referer header required by the CDN.
*   `-o, --output <PATH>`: Destination filename or prefix. If multiple time ranges are given, this acts as the prefix/folder.
*   `-b, --batch <FILE>`: Path to a JSON batch task file (or `-` to read JSON from stdin).
*   `-j, --parallel <INT>`: Concurrent downloader workers (default: 8).
*   `--transcode`: Force transcoding instead of fast sub-second stream copying.
*   `--no-align`: Disable segment boundary keyframe alignment in copy mode (might cause frozen start frames).
*   `--srt <FILE>`: Optional path to a `.srt` subtitle file. Timings will be automatically shifted/clipped. Embeds soft subtitles by default, or burns them in if `--transcode` is specified.
*   `--keep-cache`: Retain downloaded segment cache folder (`.stego_cache/<hash>/`) on successful completion (by default, it is cleared to save disk space).

### Direct Examples
1. Download a single clip:
   ```bash
   stego-hls https://example-cdn.com/playlist.m3u8 -t 08:00-12:00 --referer https://example.com/ -o clip.mp4
   ```
2. Extract multiple clips from the same stream:
   ```bash
   stego-hls https://example-cdn.com/playlist.m3u8 -t 01:00-02:00 -t 05:00-06:00 -o my_video
   ```

### JSON Batch Format (`--batch tasks.json`)
Batch tasks are defined as a JSON array of configuration objects:
```json
[
  {
    "url": "https://example-cdn.com/stream1.m3u8",
    "referer": "https://example-referrer.com/page1.html",
    "output": "download/stream1_clip.mp4",
    "time": "08:00-12:00"
  },
  {
    "url": "https://example-cdn.com/stream2.m3u8",
    "output": "download/stream2",
    "time": ["01:00-02:00", "05:00-06:00"]
  }
]
```
Run batch tasks:
```bash
stego-hls --batch tasks.json
```

---

## Python Developer API

### Basic Usage
Use the high-level manager class to fetch and clip HLS ranges:
```python
from stego_hls import HlsClipper

# Instantiate the clipper
clipper = HlsClipper()

# Extract a range losslessly
clipper.clip(
    "https://cdn4.turboviplay.com/.../index.m3u8",
    start="08:00",
    end="12:00",
    output_path="download/clip_1.mp4",
    headers={"Referer": "https://supjav.com/"}
)
```

---

## Technical Documentation
For class diagrams, low-level object-oriented specifications, sequence flows, and detailed steganographic algorithms, please refer to [TECHNICAL.md](TECHNICAL.md).
