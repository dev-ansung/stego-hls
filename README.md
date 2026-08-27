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

### CLI Usage (with `uv`)
No installation is required if you are running it inside this repository. Simply run via `uv`:
```bash
uv run python3 m3u8_downloader.py -i input.txt
```

### Library Installation (Planned)
```bash
pip install stego-hls
```

---

## CLI Usage

### Input Format
The tool accepts a structured text block from standard input (`stdin`) or an input file (`-i`).

Example input:
```text
https://supjav.com/zh/452901.html
https://cdn4.turboviplay.com/data3/6a8d6e45b0b5f/6a8d6e45b0b5f.m3u8
ABW-204
    08:00-12:00
    44:00-53:00
    2:18:00
```
*   **Line 1:** Referer URL (sent as standard page request headers).
*   **Line 2:** Master M3U8 Playlist URL.
*   **Line 3:** Filename prefix/code (e.g., `ABW-204`).
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
clipper = HlsClipper(
    master_url="https://cdn4.turboviplay.com/.../index.m3u8",
    referer="https://supjav.com/"
)

# Extract a range losslessly
clipper.clip(
    start="08:00",
    end="12:00",
    output_path="download/clip_1.mp4",
    parallel_workers=8
)
```

### Custom Decoder Registration
Inject a custom decryption class to handle proprietary obfuscations or XOR keys:
```python
from stego_hls import HlsClipper, BaseDecoder

class CustomXorDecoder(BaseDecoder):
    def __init__(self, key: int):
        self.key = key

    def decode(self, segment_data: bytes) -> bytes:
        # Strip header bytes and XOR payload
        payload = segment_data[128:]
        return bytes(b ^ self.key for b in payload)

# Register the decoder to the pipeline
clipper = HlsClipper(master_url="...")
clipper.register_decoder(CustomXorDecoder(key=0x5A))

# Execute download
clipper.clip(start="00:30", end="01:30", output_path="download/custom_clip.mp4")
```

---

## How It Works (Extraction Algorithm)
MPEG Transport Stream (TS) packets have a standard frame format of exactly **188 bytes** and always begin with the sync byte `0x47` (`G`).

When decoding steganographic images, `stego-hls`:
1.  Locates the PNG/JPEG chunk boundaries (`IEND` chunk for PNG).
2.  Scans the subsequent payload for three consecutive sync bytes spaced by exactly 188 bytes:
    $$ \text{data}[P] == 0x47 \quad\land\quad \text{data}[P + 188] == 0x47 \quad\land\quad \text{data}[P + 376] == 0x47 $$
3.  Extracts the raw segment data starting from offset $P$ to the end of the buffer, leaving a clean, unencapsulated `.ts` stream.
