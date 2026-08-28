# stego-hls Technical Design Document

This document outlines the architecture, structural components, sequence flow, and steganographic extraction algorithms for the `stego-hls` library.

---

## 1. Class Architecture

The library separates responsibilities using the **Strategy Pattern** for payload decoders, the **Facade Pattern** for user coordination, and **Inversion of Control** (Dependency Injection) to keep components pure and testable.

```mermaid
classDiagram
    class HlsClipper {
        -http_headers: dict
        -decoder: BaseDecoder
        -downloader: ParallelDownloader
        -muxer: Muxer
        +register_decoder(decoder: BaseDecoder)
        +clip(master_url: str, start: str, end: str, output_path: str)
    }

    class PlaylistParser {
        +parse_manifest(content: str, base_url: str) Timeline
        +resolve_sub_playlist(master_content: str, master_url: str) str
    }

    class Timeline {
        -segments: list[Segment]
        +total_duration: float
        +get_overlapping_segments(start_sec: float, end_sec: float) list[Segment]
    }

    class Segment {
        +index: int
        +url: str
        +duration: float
        +start_time: float
        +end_time: float
    }

    class ParallelDownloader {
        -workers: int
        -client: httpx.Client
        +download(segments: list[Segment], headers: dict) dict[int, bytes]
    }

    class BaseDecoder {
        <<abstract>>
        +decode(raw_bytes: bytes) bytes
    }

    class StegoDecoder {
        +decode(raw_bytes: bytes) bytes
    }

    class PassthroughDecoder {
        +decode(raw_bytes: bytes) bytes
    }

    class Muxer {
        <<interface>>
        +concatenate_and_clip(payloads: dict, relative_start: float, relative_end: float, output_path: str)
    }

    class FfmpegMuxer {
        -transcode: bool
        +concatenate_and_clip(payloads: dict, relative_start: float, relative_end: float, output_path: str)
    }

    HlsClipper --> PlaylistParser
    HlsClipper --> ParallelDownloader
    HlsClipper --> BaseDecoder
    HlsClipper --> Muxer
    PlaylistParser ..> Timeline
    Timeline "1" *-- "many" Segment
    BaseDecoder <|-- StegoDecoder
    BaseDecoder <|-- PassthroughDecoder
    Muxer <|.. FfmpegMuxer
```

---

## 2. Core Components

### Domain & Timeline Models
*   **`Segment`**: An immutable data model containing the HLS segment index, resolved URL, duration, and absolute timing bounds relative to the video start.
*   **`Timeline`**: A collection container for all segments in a manifest. It calculates total stream duration and computes the minimal set of segment indices that overlap with any target clipping range $[T_{start}, T_{end}]$.

### Network & Parsing Engines
*   **`PlaylistParser`**: A pure stateless parsing helper that reads manifest text content and constructs the `Timeline` mapping without making external network calls.
*   **`ParallelDownloader`**: An I/O-bound concurrency runner that uses thread pools and a configurable HTTP client to fetch raw segment chunks in parallel.

### Decoders (Strategy Pattern)
*   **`BaseDecoder`**: Abstract base class defining the signature for transforming raw downloaded bytes into valid Transport Stream (.ts) data.
*   **`PassthroughDecoder`**: Used for standard unencrypted HLS streams, returning segment bytes untouched.
*   **`StegoDecoder`**: Finds the boundary where visual image metadata ends and video packet payloads begin, parsing out valid TS sync packets.

### Stream Muxer (Piping Compiler)
*   **`Muxer`**: A protocol defining in-memory concatenation and output generation.
*   **`FfmpegMuxer`**: Feeds the concatenated in-memory byte segments directly into FFmpeg's `stdin` (`pipe:0`) and compiles the final MP4. By using system stream piping instead of intermediate files on disk, it avoids unnecessary disk I/O.

### Coordinator Facade
*   **`HlsClipper`**: The orchestrator facade that wires together the injected downloader, decoder, and muxer instances to execute a clip sequence.

---

## 3. Data Flow Sequence

```mermaid
sequenceDiagram
    actor Developer
    participant Clipper as HlsClipper
    participant Parser as PlaylistParser
    participant Downloader as ParallelDownloader
    participant Decoder as StegoDecoder
    participant Muxer as Muxer
    
    Developer->>Clipper: clip(url, "08:00", "12:00", "output.mp4")
    Clipper->>Parser: parse_manifest(content, base_url)
    Parser-->>Clipper: Timeline (contains Segment list)
    
    Note over Clipper: Calculates target segments &<br/>relative start/end time offsets
    
    Clipper->>Downloader: download(target_segments, headers)
    Downloader-->>Clipper: Dict[index, raw_bytes]
    
    loop For each segment index
        Clipper->>Decoder: decode(raw_bytes)
        Decoder-->>Clipper: ts_bytes
    end
    
    Clipper->>Muxer: concatenate_and_clip(Dict[index, ts_bytes], rel_start, rel_end, "output.mp4")
    Note over Muxer: Spawns FFmpeg<br/>Pipes TS bytes to stdin<br/>Saves MP4 losslessly
    Muxer-->>Clipper: Done
    Clipper-->>Developer: Success!
```

---

## 4. Steganography Payload Boundary Finding Algorithm

HLS segments wrap standard Transport Stream (TS) packets. Every TS packet is exactly **188 bytes** long and begins with a sync byte `0x47` (character `G` in ASCII).

In steganographic envelopes (e.g. mock `.png` or `.jpeg` files), the video data is appended after the official image data chunks. To isolate the video payload, the `StegoDecoder` performs a boundary check:
1.  Locates the image format end metadata boundary (e.g., the PNG `IEND` chunk).
2.  Starts a rolling window search beginning immediately after this chunk.
3.  Evaluates whether three consecutive sync bytes appear exactly 188 bytes apart:
    $$ \text{data}[P] == 0x47 \quad\land\quad \text{data}[P + 188] == 0x47 \quad\land\quad \text{data}[P + 376] == 0x47 $$
4.  Identifies $P$ as the valid byte offset starting point, and returns the slice from $P$ onwards.
