import argparse
import json
import os
import sys
import urllib.parse
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


def run_batch(tasks: list[dict], *, parallel: int, transcode: bool) -> None:
    """Processes a batch array of clipping task configurations."""
    downloader = ParallelDownloader(workers=parallel)
    muxer = FfmpegMuxer(transcode=transcode)
    clipper = HlsClipper(downloader=downloader, muxer=muxer)
    
    for task_idx, task in enumerate(tasks):
        url = task.get("url")
        if not url:
            print(f"Skipping task {task_idx}: missing 'url' key.", file=sys.stderr)
            continue
            
        referer = task.get("referer")
        output = task.get("output")
        time_spec = task.get("time")
        
        # Resolve output destination prefix
        if not output:
            parsed_url = urllib.parse.urlparse(url)
            base_name = os.path.basename(parsed_url.path.strip("/"))
            output_prefix = os.path.splitext(base_name)[0] or "download_clip"
        else:
            output_prefix = output

        # Parse timestamp clipping ranges
        ranges: list[tuple[float, float | None, str]] = []
        if isinstance(time_spec, str):
            time_spec = [time_spec]
            
        if time_spec:
            for item in time_spec:
                if '-' in item:
                    start_str, end_str = item.split('-')
                    start = parse_timestamp(start_str)
                    end = parse_timestamp(end_str)
                    ranges.append((start, end, item))
                else:
                    start = parse_timestamp(item)
                    ranges.append((start, None, item))
        else:
            ranges.append((0.0, None, "full"))

        # Setup standard request headers
        headers = {}
        if referer:
            headers["Referer"] = referer
            
        headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

        for start_time, end_time, raw_range_str in ranges:
            sanitized_range = raw_range_str.replace(":", "_").replace("-", "-")
            
            if output_prefix.endswith(".mp4") and len(ranges) == 1:
                output_path = Path(output_prefix)
            elif output_prefix.endswith(".mp4"):
                prefix_no_ext = output_prefix[:-4]
                output_path = Path(f"{prefix_no_ext}.{sanitized_range}.mp4")
            else:
                output_path = Path(f"{output_prefix}.{sanitized_range}.mp4")
                
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            print(f"\nProcessing: {url}")
            if referer:
                print(f"Referer: {referer}")
            print(f"Output to: {output_path}")
            
            start_str = str(start_time)
            end_str = str(end_time) if end_time is not None else "99999999.0"
            
            try:
                clipper.clip(
                    url,
                    start=start_str,
                    end=end_str,
                    output_path=output_path,
                    headers=headers
                )
                print(f"Successfully generated: {output_path}")
            except Exception as e:  # noqa: BLE001
                print(f"Failed to clip {raw_range_str}: {e}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="M3U8 Steganographic Downloader and Clipper CLI")
    parser.add_argument("url", nargs="?", help="HLS M3U8 manifest URL or HTML player page URL.")
    parser.add_argument("-t", "--time", action="append", help="Target timing range (e.g. 08:00-12:00 or 2:18:00). Can be specified multiple times.")
    parser.add_argument("-r", "--referer", help="Optional Referer URL header required by CDN.")
    parser.add_argument("-o", "--output", help="Destination file path or prefix.")
    parser.add_argument("-b", "--batch", help="Path to a JSON batch task file (or '-' to read JSON from stdin).")
    parser.add_argument("--transcode", action="store_true", help="Force transcoding instead of fast stream copying.")
    parser.add_argument("-j", "--parallel", type=int, default=8, help="Number of concurrent segment downloads.")
    
    args = parser.parse_args()
    
    # Batch JSON Processing
    if args.batch:
        if args.batch == "-":
            tasks_data = sys.stdin.read()
        else:
            with open(args.batch, "r", encoding="utf-8") as f:
                tasks_data = f.read()
                
        try:
            tasks = json.loads(tasks_data)
        except Exception as e:  # noqa: BLE001
            print(f"Error parsing batch JSON: {e}", file=sys.stderr)
            sys.exit(1)
            
        if not isinstance(tasks, list):
            print("Batch JSON must be a list of task configurations.", file=sys.stderr)
            sys.exit(1)
            
        run_batch(tasks, parallel=args.parallel, transcode=args.transcode)
        return
        
    # Direct single-line argument parsing
    if not args.url:
        parser.print_help()
        sys.exit(1)
        
    task = {
        "url": args.url,
        "referer": args.referer,
        "output": args.output,
        "time": args.time
    }
    
    run_batch([task], parallel=args.parallel, transcode=args.transcode)


if __name__ == "__main__":
    main()
