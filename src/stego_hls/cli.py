import argparse
import json
import os
import sys
import urllib.parse

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

def run_batch(tasks: list[dict], *, parallel: int, transcode: bool, no_align: bool = False, srt: str | None = None, keep_cache: bool = False) -> None:
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
        no_align_task = task.get("no_align", no_align)
        srt_task = task.get("srt", srt)
        keep_cache_task = task.get("keep_cache", keep_cache)
        
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
            if not referer.startswith(("http://", "https://")):
                referer = f"https://{referer}"
            headers["Referer"] = referer
            
        headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

        for start_time, end_time, raw_range_str in ranges:
            if output_prefix.endswith(".mp4") and len(ranges) == 1:
                target_prefix = output_prefix
            elif output_prefix.endswith(".mp4"):
                target_prefix = output_prefix[:-4]
            else:
                target_prefix = output_prefix
                
            print(f"\nProcessing: {url}")
            if referer:
                print(f"Referer: {referer}")
            
            start_str = str(start_time)
            end_str = str(end_time) if end_time is not None else "99999999.0"
            
            try:
                final_path = clipper.clip(
                    url,
                    start=start_str,
                    end=end_str,
                    output_prefix=target_prefix,
                    headers=headers,
                    align_bounds=not no_align_task,
                    srt_path=srt_task,
                    keep_cache=keep_cache_task
                )
                print(f"Successfully generated: {final_path}")
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
    parser.add_argument("--no-align", action="store_true", help="Disable segment boundary alignment in copy mode (might cause frozen start frames).")
    parser.add_argument("--srt", help="Optional path to a .srt subtitle file to embed or burn in.")
    parser.add_argument("--keep-cache", action="store_true", help="Retain downloaded segments cache folder after successful run.")
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
            
        run_batch(tasks, parallel=args.parallel, transcode=args.transcode, no_align=args.no_align, srt=args.srt, keep_cache=args.keep_cache)
        return
        
    # Direct single-line argument parsing
    if not args.url:
        parser.print_help()
        sys.exit(1)
        
    task = {
        "url": args.url,
        "referer": args.referer,
        "output": args.output,
        "time": args.time,
        "srt": args.srt,
        "keep_cache": args.keep_cache
    }
    
    run_batch([task], parallel=args.parallel, transcode=args.transcode, no_align=args.no_align, srt=args.srt, keep_cache=args.keep_cache)


if __name__ == "__main__":
    main()
