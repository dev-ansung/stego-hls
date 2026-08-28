#!/usr/bin/env python3
import argparse
import sys
import os
import re
import subprocess
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
import httpx
from tqdm import tqdm

# Constants
MPEG_TS_PACKET_SIZE = 188
SYNC_BYTE = 0x47

def parse_timestamp(t_str: str) -> float:
    """
    Parse a timestamp string in HH:MM:SS or MM:SS format into float seconds.
    """
    parts = t_str.strip().split(':')
    if len(parts) == 2:
        return float(parts[0]) * 60 + float(parts[1])
    elif len(parts) == 3:
        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    else:
        raise ValueError(f"Invalid timestamp format: {t_str}")

def parse_input_text(text: str):
    """
    Parse the input text block to extract:
    - referer
    - master_url
    - prefix
    - ranges (list of tuples (start, end, raw_str))
    """
    lines = [line.strip() for line in text.strip().split('\n') if line.strip()]
    if len(lines) < 3:
        raise ValueError("Input text must contain at least referer, master_url, and file prefix.")
    
    referer = lines[0]
    master_url = lines[1]
    prefix = lines[2]
    
    ranges = []
    for line in lines[3:]:
        line_clean = line.strip()
        if not line_clean:
            continue
        
        # Check if it's a range like "08:00-12:00"
        if '-' in line_clean:
            start_str, end_str = line_clean.split('-')
            start = parse_timestamp(start_str)
            end = parse_timestamp(end_str)
            ranges.append((start, end, line_clean))
        else:
            # Single timestamp "2:18:00" (starts at timestamp to the end of the video)
            start = parse_timestamp(line_clean)
            ranges.append((start, None, line_clean))
            
    return referer, master_url, prefix, ranges

def find_ts_start_offset(segment_data: bytes) -> int:
    """
    Find the start offset of MPEG-TS payload in the segment data
    by scanning for three consecutive 0x47 sync bytes spaced by 188 bytes.
    """
    iend_idx = segment_data.find(b"IEND")
    if iend_idx == -1:
        search_start = 0
    else:
        search_start = iend_idx + 12
        
    sub_data = segment_data[search_start:]
    
    for offset in range(len(sub_data) - MPEG_TS_PACKET_SIZE * 2):
        if (sub_data[offset] == SYNC_BYTE and 
            sub_data[offset + MPEG_TS_PACKET_SIZE] == SYNC_BYTE and 
            sub_data[offset + MPEG_TS_PACKET_SIZE * 2] == SYNC_BYTE):
            return search_start + offset
            
    return -1

def download_and_extract_segment(idx: int, url: str, client: httpx.Client) -> tuple[int, bytes]:
    """
    Download segment, extract the TS payload, and return (idx, ts_bytes).
    """
    headers = None
    if "googleusercontent.com" in url:
        headers = {"Referer": None, "Origin": None}
        
    resp = client.get(url, headers=headers, timeout=30.0)
    resp.raise_for_status()
    
    segment_data = resp.content
    ts_offset = find_ts_start_offset(segment_data)
    if ts_offset == -1:
        raise ValueError(f"Segment {idx} is not a valid steganographic HLS stream.")
        
    return idx, segment_data[ts_offset:]

def process_playlist(master_url: str, referer: str) -> tuple[str, list[tuple[str, float]]]:
    """
    Fetches the master playlist, finds the highest bandwidth stream,
    fetches its sub-playlist, and extracts segment URLs and durations.
    Returns (sub_playlist_url, list of (segment_url, duration)).
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": referer
    }
    if referer:
        parsed_ref = urllib.parse.urlparse(referer)
        headers["Origin"] = f"{parsed_ref.scheme}://{parsed_ref.netloc}"
    
    with httpx.Client(headers=headers, follow_redirects=True, timeout=10.0) as client:
        # Fetch Master
        resp = client.get(master_url)
        resp.raise_for_status()
        master_content = resp.text
        
        # Parse stream playlists sequentially or by tags
        lines = [line.strip() for line in master_content.strip().split('\n') if line.strip()]
        sub_playlists = []
        for i, line in enumerate(lines):
            if line.startswith("#EXT-X-STREAM-INF") and i + 1 < len(lines):
                next_line = lines[i+1]
                if not next_line.startswith("#"):
                    sub_playlists.append(urllib.parse.urljoin(master_url, next_line))
        
        # Fallback if no sub-playlists found
        if not sub_playlists:
            if "#EXTINF" in master_content:
                sub_url = master_url
                sub_content = master_content
            else:
                for line in lines:
                    if not line.startswith("#") and (".m3u8" in line or ".txt" in line or "playlist" in line):
                        sub_playlists.append(urllib.parse.urljoin(master_url, line))
                        
                if not sub_playlists:
                    raise ValueError("No sub-playlists found in master playlist.")
                    
        if sub_playlists:
            # Select highest quality (usually last in master)
            sub_url = sub_playlists[-1]
            resp = client.get(sub_url)
            resp.raise_for_status()
            sub_content = resp.text
            
        # Parse segments and durations
        segments = []
        lines = sub_content.strip().split('\n')
        current_duration = 0.0
        
        for line in lines:
            line = line.strip()
            if line.startswith("#EXTINF:"):
                dur_match = re.match(r"#EXTINF:([0-9.]+)", line)
                if dur_match:
                    current_duration = float(dur_match.group(1))
            elif line and not line.startswith("#"):
                segments.append((urllib.parse.urljoin(sub_url, line), current_duration))
                
        return sub_url, segments

def main():
    parser = argparse.ArgumentParser(description="M3U8 Steganographic Downloader and Clipper CLI")
    parser.add_argument("-i", "--input", help="Path to input text file. If omitted, reads from stdin.")
    parser.add_argument("-o", "--output-dir", default="download", help="Directory to save the output MP4 files.")
    parser.add_argument("--transcode", action="store_true", help="Force transcoding instead of fast stream copying.")
    parser.add_argument("-j", "--parallel", type=int, default=8, help="Number of concurrent segment downloads.")
    
    args = parser.parse_args()
    
    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            input_text = f.read()
    else:
        print("Reading input block from standard input... (Press Ctrl+D when finished)")
        input_text = sys.stdin.read()
        
    try:
        referer, master_url, prefix, ranges = parse_input_text(input_text)
    except Exception as e:
        print(f"Error parsing input text: {e}", file=sys.stderr)
        sys.exit(1)
        
    print(f"Parsed Referer: {referer}")
    print(f"Parsed Master Playlist: {master_url}")
    print(f"Parsed File Prefix: {prefix}")
    print(f"Parsed Ranges: {len(ranges)} clip(s) to download.")
    
    # Process playlist
    print("Fetching and parsing playlist...")
    try:
        sub_url, segments = process_playlist(master_url, referer)
        print(f"Playlist has {len(segments)} segments.")
    except Exception as e:
        print(f"Error loading playlist: {e}", file=sys.stderr)
        sys.exit(1)
        
    # Calculate cumulative durations
    segment_timeline = []
    cum_time = 0.0
    for idx, (url, duration) in enumerate(segments):
        start = cum_time
        end = cum_time + duration
        segment_timeline.append({
            "idx": idx,
            "url": url,
            "duration": duration,
            "start": start,
            "end": end
        })
        cum_time = end
        
    total_duration = cum_time
    print(f"Total video duration: {total_duration:.2f} seconds (~{total_duration/60:.1f} minutes).")
    
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Process each range
    for start_time, end_time, raw_range_str in ranges:
        if end_time is None:
            end_time = total_duration
            
        print(f"\nProcessing section: {raw_range_str} ({start_time}s to {end_time}s)")
        
        # Find overlapping segments
        overlapping_segs = []
        for seg in segment_timeline:
            if seg["start"] < end_time and seg["end"] > start_time:
                overlapping_segs.append(seg)
                
        if not overlapping_segs:
            print(f"No segments overlap with range {raw_range_str}. Skipping.", file=sys.stderr)
            continue
            
        first_seg_idx = overlapping_segs[0]["idx"]
        last_seg_idx = overlapping_segs[-1]["idx"]
        first_seg_start = overlapping_segs[0]["start"]
        
        relative_start = start_time - first_seg_start
        relative_end = end_time - first_seg_start
        
        print(f"Selected segments: {first_seg_idx} to {last_seg_idx} ({len(overlapping_segs)} segments total).")
        print(f"Relative cut points: {relative_start:.2f}s to {relative_end:.2f}s within the downloaded sequence.")
        
        # Download segment payloads in parallel
        download_headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        if referer:
            download_headers["Referer"] = referer
            parsed_ref = urllib.parse.urlparse(referer)
            download_headers["Origin"] = f"{parsed_ref.scheme}://{parsed_ref.netloc}"
        
        segment_payloads = {}
        print("Downloading and extracting segments...")
        with httpx.Client(headers=download_headers, follow_redirects=True, timeout=60.0) as client:
            with ThreadPoolExecutor(max_workers=args.parallel) as executor:
                futures = {
                    executor.submit(download_and_extract_segment, seg["idx"], seg["url"], client): seg 
                    for seg in overlapping_segs
                }
                
                for future in tqdm(as_completed(futures), total=len(futures), desc="Download Progress"):
                    try:
                        seg_idx, ts_bytes = future.result()
                        segment_payloads[seg_idx] = ts_bytes
                    except Exception as e:
                        # Cancel remaining tasks on failure
                        print(f"\nError downloading segment: {e}", file=sys.stderr)
                        for f in futures:
                            f.cancel()
                        sys.exit(1)
                        
        # Merge TS packets in sequential order
        temp_ts_path = os.path.join(args.output_dir, f"temp_{prefix}_{first_seg_idx}_{last_seg_idx}.ts")
        with open(temp_ts_path, "wb") as f:
            for seg_idx in sorted(segment_payloads.keys()):
                f.write(segment_payloads[seg_idx])
                
        # Remux/Transcode to output filename
        sanitized_range = raw_range_str.replace(":", "_").replace("-", "-")
        output_filename = f"{prefix}.{sanitized_range}.mp4"
        output_path = os.path.join(args.output_dir, output_filename)
        
        print(f"Clipping and converting to {output_filename}...")
        
        # Build ffmpeg command
        ffmpeg_cmd = ["ffmpeg", "-y"]
        
        if args.transcode:
            ffmpeg_cmd.extend([
                "-ss", f"{relative_start:.3f}",
                "-to", f"{relative_end:.3f}",
                "-i", temp_ts_path,
                "-c:v", "libx264",
                "-c:a", "aac",
                output_path
            ])
        else:
            ffmpeg_cmd.extend([
                "-ss", f"{relative_start:.3f}",
                "-to", f"{relative_end:.3f}",
                "-i", temp_ts_path,
                "-c", "copy",
                output_path
            ])
            
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        
        # Cleanup temporary TS file
        if os.path.exists(temp_ts_path):
            os.remove(temp_ts_path)
            
        if result.returncode == 0:
            print(f"Successfully generated: {output_path}")
        else:
            print(f"Clipping failed for {raw_range_str}.", file=sys.stderr)
            print(result.stderr, file=sys.stderr)

if __name__ == "__main__":
    main()
