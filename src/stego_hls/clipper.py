import os
import re
import urllib.parse
from pathlib import Path

import httpx

from stego_hls.decoders import BaseDecoder, StegoDecoder
from stego_hls.downloader import ParallelDownloader
from stego_hls.muxer import FfmpegMuxer, Muxer
from stego_hls.playlist import PlaylistParser

type DecodedPayloads = dict[int, bytes]


class HlsClipper:
    def __init__(self, 
                 *, 
                 downloader: ParallelDownloader | None = None,
                 decoder: BaseDecoder | None = None,
                 muxer: Muxer | None = None) -> None:
        self.downloader = downloader or ParallelDownloader()
        self.decoder = decoder or StegoDecoder()
        self.muxer = muxer or FfmpegMuxer()

    def clip(self, 
             master_url: str, 
             *, 
             start: str, 
             end: str, 
             output_prefix: str | Path,
             headers: dict[str, str] | None = None,
             align_bounds: bool = True) -> Path:
        """Coordinates parsing, timeline slicing, parallel fetching, decoding, and muxing.
        
        Returns:
            Path: The final resolved output video file path.
        """
        request_headers = headers or {}
        
        # 1. Fetch master playlist raw text (Single-Request)
        with httpx.Client(headers=request_headers, follow_redirects=True) as client:
            resp = client.get(master_url)
            resp.raise_for_status()
            master_text = resp.text
            
            # Scrape HTML page if it's an iframe player
            if master_text.strip().lower().startswith("<!doctype") or "<html" in master_text.lower():
                embedded_urls = re.findall(r"['\"](https?://[^\'\"]+\.(?:m3u8|txt)[^\'\"]*)['\"]", master_text)
                if not embedded_urls:
                    embedded_urls = re.findall(r"['\"]([^\'\"]+\.(?:m3u8|txt)[^\'\"]*)['\"]", master_text)
                    embedded_urls = [urllib.parse.urljoin(master_url, u) for u in embedded_urls]
                if not embedded_urls:
                    raise ValueError("No M3U8 streaming URLs found in player iframe HTML.")
                sub_url = embedded_urls[0]
            else:
                sub_url = PlaylistParser.resolve_sub_playlist(master_text, master_url=master_url)
                
            sub_text = client.get(sub_url).text

        # 2. Parse sub-playlist timeline
        timeline = PlaylistParser.parse_manifest(sub_text, base_url=sub_url)

        # 3. Time bounds mapping
        start_sec = self._parse_time(start)
        end_sec = self._parse_time(end)
        
        overlapping = timeline.get_overlapping_segments(start_sec=start_sec, end_sec=end_sec)
        if not overlapping:
            raise ValueError("No media segments found overlapping the target clipping range.")

        first_seg_start = overlapping[0].start_time
        
        # Query Muxer properties to determine if keyframe boundary alignment is needed
        requires_alignment = getattr(self.muxer, "requires_keyframe_alignment", True)
        if requires_alignment and align_bounds:
            relative_start = 0.0
        else:
            relative_start = start_sec - first_seg_start
            
        relative_end = end_sec - first_seg_start

        # 4. Resolve output file path dynamically based on aligned start/end times
        prefix_path = Path(output_prefix)
        if prefix_path.is_dir() or str(prefix_path).endswith(("/", "\\")):
            parsed_url = urllib.parse.urlparse(master_url)
            base_name = os.path.basename(parsed_url.path.strip("/"))
            prefix_path = prefix_path / (os.path.splitext(base_name)[0] or "download_clip")

        actual_start_sec = first_seg_start + relative_start
        actual_end_sec = min(end_sec, timeline.total_duration)
        
        output_path = self._resolve_output_path(prefix_path, actual_start_sec, actual_end_sec, end)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if requires_alignment and align_bounds and start_sec != first_seg_start:
            print(f"[stego-hls] Aligning start time from {self._format_duration(start_sec)} to {self._format_duration(first_seg_start)} (segment boundary keyframe) to prevent frozen frames in copy mode. Use --transcode for exact frame-level cuts.")

        # 5. Download segment buffers
        raw_payloads = self.downloader.download(overlapping, request_headers)

        # 6. Decode segments in memory
        decoded_payloads: DecodedPayloads = {
            index: self.decoder.decode(raw_data)
            for index, raw_data in raw_payloads.items()
        }

        # 7. Stream directly into Muxer stdin
        self.muxer.concatenate_and_clip(
            decoded_payloads, 
            relative_start=relative_start, 
            relative_end=relative_end, 
            output_path=str(output_path)
        )
        
        return output_path

    def _resolve_output_path(self, prefix: Path, start_sec: float, end_sec: float, end_original: str) -> Path:
        """Determines the final Path based on whether a directory prefix or explicit file was passed."""
        if prefix.suffix == ".mp4":
            return prefix
            
        start_str = self._format_duration_suffix(start_sec)
        if end_original in (None, "99999999.0", "99999999"):
            suffix = start_str
        else:
            end_str = self._format_duration_suffix(end_sec)
            suffix = f"{start_str}-{end_str}"
            
        return Path(f"{prefix}.{suffix}.mp4")

    def _format_duration_suffix(self, seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        if h > 0:
            return f"{h:02d}_{m:02d}_{s:02d}"
        return f"{m:02d}_{s:02d}"

    def _format_duration(self, seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def _parse_time(self, time_str: str, /) -> float:
        parts = time_str.strip().split(':')
        match parts:
            case [s]:
                return float(s)
            case [m, s]:
                return float(m) * 60 + float(s)
            case [h, m, s]:
                return float(h) * 3600 + float(m) * 60 + float(s)
            case _:
                raise ValueError(f"Invalid timestamp format: {time_str}")
