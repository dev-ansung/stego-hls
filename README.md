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
uvx --from git+https://github.com/dev-ansung/m3u8-downloader.git m3u8-downloader -i input.txt
```

### Local Development Usage (via `uv`)
If you have cloned the repository locally, run the executable script directly:
```bash
uv run m3u8_downloader.py -i input.txt
```

---

## CLI Usage

### Input Format
The tool accepts a structured text block from standard input (`stdin`) or an input file (`-i`).

Example input:
```text
https://example-referrer.com/page.html
https://example-cdn.com/stream/playlist.m3u8
example-video
    08:00-12:00
    44:00-53:00
    2:18:00
```
*   **Line 1:** Referer URL (sent as standard page request headers).
*   **Line 2:** Master M3U8 Playlist URL.
*   **Line 3:** Filename prefix/code (e.g., `example-video`).
*   **Line 4+:** Timestamp ranges or single start timestamps (which slice from the start point to the end of the video).

### CLI Command Options
```text
options:
  -h, --help            show this help message and exit
  -i INPUT, --input INPUT
                        Path to input text file. If omitted, reads from stdin.
  -o OUTPUT_DIR, --output-dir OUTPUT_DIR
                        Directory to save the output MP4 files (default: "download").
  --transcode           Force transcoding instead of fast stream copying.
  -j PARALLEL, --parallel PARALLEL
                        Number of concurrent segment downloads (default: 8).
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
