import re
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
             output_path: str | Path,
             headers: dict[str, str] | None = None) -> None:
        """Coordinates parsing, timeline slicing, parallel fetching, decoding, and muxing."""
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
                
                if embedded_urls:
                    master_url = embedded_urls[-1]
                    resp = client.get(master_url)
                    resp.raise_for_status()
                    master_text = resp.text
                else:
                    raise ValueError("Could not find any HLS stream URLs embedded in the HTML page.")

            # 2. Resolve sub-playlist (if master is a multi-variant manifest)
            sub_url = PlaylistParser.resolve_sub_playlist(master_text, master_url=master_url)
            if sub_url != master_url:
                resp = client.get(sub_url)
                resp.raise_for_status()
                sub_text = resp.text
            else:
                sub_text = master_text

        # 3. Parse manifest
        timeline = PlaylistParser.parse_manifest(sub_text, base_url=sub_url)

        # 4. Time bounds mapping
        start_sec = self._parse_time(start)
        end_sec = self._parse_time(end)
        
        overlapping = timeline.get_overlapping_segments(start_sec=start_sec, end_sec=end_sec)
        if not overlapping:
            raise ValueError("No media segments found overlapping the target clipping range.")

        first_seg_start = overlapping[0].start_time
        relative_start = start_sec - first_seg_start
        relative_end = end_sec - first_seg_start

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
                
# Import inside function if needed, or import standard urllib
import urllib.parse
