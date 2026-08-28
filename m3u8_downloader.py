#!/usr/bin/env python3
import os
import re
import sys
import urllib.parse

import httpx

# Insert src/ to system path to prioritize local library files
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from stego_hls.cli import main
from stego_hls.playlist import PlaylistParser


def process_playlist(url: str, referer: str | None = None) -> tuple[str, list[tuple[str, float]]]:
    """Compatibility wrapper for extract_stream.py to parse HLS playlists."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": referer
    }
    if referer:
        parsed_ref = urllib.parse.urlparse(referer)
        headers["Origin"] = f"{parsed_ref.scheme}://{parsed_ref.netloc}"
        
    with httpx.Client(headers=headers, follow_redirects=True, timeout=10.0) as client:
        resp = client.get(url)
        resp.raise_for_status()
        master_content = resp.text
        
        # Check if the content is HTML (usually iframe players containing the manifest link)
        if master_content.strip().lower().startswith("<!doctype") or "<html" in master_content.lower():
            embedded_urls = re.findall(r"['\"](https?://[^\'\"]+\.(?:m3u8|txt)[^\'\"]*)['\"]", master_content)
            if not embedded_urls:
                embedded_urls = re.findall(r"['\"]([^\'\"]+\.(?:m3u8|txt)[^\'\"]*)['\"]", master_content)
                embedded_urls = [urllib.parse.urljoin(url, u) for u in embedded_urls]
            
            if embedded_urls:
                url = embedded_urls[-1]
                resp = client.get(url)
                resp.raise_for_status()
                master_content = resp.text
            else:
                raise ValueError("Could not find any HLS stream URLs embedded in the HTML page.")
        
        sub_url = PlaylistParser.resolve_sub_playlist(master_content, master_url=url)
        if sub_url != url:
            resp = client.get(sub_url)
            resp.raise_for_status()
            sub_content = resp.text
        else:
            sub_content = master_content
            
        timeline = PlaylistParser.parse_manifest(sub_content, base_url=sub_url)
        segments = [(seg.url, seg.duration) for seg in timeline.segments]
        return sub_url, segments

def download_and_extract_segment(idx: int, url: str, client: httpx.Client, referer: str | None = None) -> tuple[int, bytes]:
    """Compatibility helper to download and decode a single segment."""
    from stego_hls.decoders import StegoDecoder
    from stego_hls.downloader import ParallelDownloader
    from stego_hls.playlist import Segment
    
    downloader = ParallelDownloader(client=client)
    seg = Segment(index=idx, url=url, duration=0.0, start_time=0.0, end_time=0.0)
    
    headers = {}
    if referer:
        headers["Referer"] = referer
        
    raw_payloads = downloader.download([seg], headers=headers)
    raw_data = raw_payloads[idx]
    
    decoder = StegoDecoder()
    ts_bytes = decoder.decode(raw_data)
    return idx, ts_bytes

if __name__ == "__main__":
    main()
