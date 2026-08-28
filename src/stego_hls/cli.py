import argparse
import sys
from pathlib import Path

from stego_hls.clipper import HlsClipper
from stego_hls.downloader import ParallelDownloader
from stego_hls.muxer import FfmpegMuxer


def parse_timestamp(t_str: str) -> float:
    """Parse a timestamp string in HH:MM:SS or MM:SS format into float seconds."""
    parts = t_str.strip().split(':')
    match parts:
        case [s]:
            return float(s)
        case [m, s]:
            return float(m) * 60 + float(s)
        case [h, m, s]:
            return float(h) * 3600 + float(m) * 60 + float(s)
        case _:
            raise ValueError(f"Invalid timestamp format: {t_str}")


def parse_input_text(text: str) -> tuple[str, str, str, list[tuple[float, float | None, str]]]:
    """
    Parse the input text block to extract:
    - referer
    - master_url
    - prefix
    - list of ranges as (start_sec, end_sec_or_None, raw_range_str)
    """
    lines = [line.strip() for line in text.strip().split('\n') if line.strip()]
    if len(lines) < 3:
        raise ValueError("Input text must contain at least referer, master_url, and file prefix.")
    
    referer = lines[0]
    master_url = lines[1]
    prefix = lines[2]
    
    ranges: list[tuple[float, float | None, str]] = []
    for line in lines[3:]:
        line_clean = line.strip()
        if not line_clean:
            continue
        
        if '-' in line_clean:
            start_str, end_str = line_clean.split('-')
            start = parse_timestamp(start_str)
            end = parse_timestamp(end_str)
            ranges.append((start, end, line_clean))
        else:
            start = parse_timestamp(line_clean)
            ranges.append((start, None, line_clean))
            
    return referer, master_url, prefix, ranges


def main() -> None:
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
    except Exception as e:  # noqa: BLE001
        print(f"Error parsing input text: {e}", file=sys.stderr)
        sys.exit(1)
        
    print(f"Parsed Referer: {referer}")
    print(f"Parsed Master Playlist: {master_url}")
    print(f"Parsed File Prefix: {prefix}")
    print(f"Parsed Ranges: {len(ranges)} clip(s) to download.")
    
    # Instantiate clipper with custom downloader & muxer
    downloader = ParallelDownloader(workers=args.parallel)
    muxer = FfmpegMuxer(transcode=args.transcode)
    clipper = HlsClipper(downloader=downloader, muxer=muxer)
    
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for start_time, end_time, raw_range_str in ranges:
        sanitized_range = raw_range_str.replace(":", "_").replace("-", "-")
        output_filename = f"{prefix}.{sanitized_range}.mp4"
        output_path = output_dir / output_filename
        
        print(f"\nProcessing section: {raw_range_str} to {output_filename}...")
        
        # Clip expects HH:MM:SS format or raw seconds as string
        start_str = str(start_time)
        
        # If end is None, we need to let HlsClipper handle end dynamically.
        # But HlsClipper expects absolute time strings.
        # We can pass "9999999.0" or a large number to HlsClipper to slice until the end!
        end_str = str(end_time) if end_time is not None else "99999999.0"
        
        try:
            clipper.clip(
                master_url,
                start=start_str,
                end=end_str,
                output_path=output_path,
                headers={"Referer": referer, "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            )
            print(f"Successfully generated: {output_path}")
        except Exception as e:  # noqa: BLE001
            print(f"Clipping failed for {raw_range_str}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
