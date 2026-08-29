import time
import urllib.parse
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

from stego_hls.cache import FileSegmentCache, SegmentCache
from stego_hls.playlist import Segment

type ProgressCallback = Callable[[int, int], None]


class ParallelDownloader:
    def __init__(self, 
                 *, 
                 workers: int = 8, 
                 client: httpx.Client | None = None,
                 cache: SegmentCache | None = None,
                 max_retries: int = 3,
                 backoff_factor: float = 1.0) -> None:
        self.workers = workers
        self.client = client or httpx.Client(follow_redirects=True, timeout=30.0)
        self.cache = cache if cache is not None else FileSegmentCache()
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    def download(self, 
                 segments: list[Segment], 
                 headers: dict[str, str], 
                 stream_hash: str,
                 *, 
                 progress_cb: ProgressCallback | None = None) -> dict[int, bytes]:
        """Downloads segment bytes concurrently using the configured HTTP client."""
        raw_payloads: dict[int, bytes] = {}

        def fetch_segment(seg: Segment) -> tuple[int, bytes]:
            # 1. Cache hit check
            cached_data = self.cache.get(stream_hash, seg.index)
            if cached_data is not None:
                return seg.index, cached_data

            # 2. Cache miss: Fetch with retry loop
            req_headers = {}
            if "User-Agent" in headers:
                req_headers["User-Agent"] = headers["User-Agent"]
            if "Referer" in headers and "googleusercontent.com" not in seg.url:
                req_headers["Referer"] = headers["Referer"]
                parsed_ref = urllib.parse.urlparse(headers["Referer"])
                req_headers["Origin"] = f"{parsed_ref.scheme}://{parsed_ref.netloc}"

            retries = 0
            while True:
                try:
                    resp = self.client.get(seg.url, headers=req_headers if req_headers else None)
                    resp.raise_for_status()
                    data = resp.content
                    
                    # Store in cache
                    self.cache.set(stream_hash, seg.index, data)
                    return seg.index, data
                except (httpx.HTTPError, OSError) as e:
                    retries += 1
                    if retries > self.max_retries:
                        raise RuntimeError(
                            f"Failed to download segment {seg.index} after {self.max_retries} retries: {e}"
                        ) from e
                    
                    if self.backoff_factor > 0.0:
                        sleep_time = self.backoff_factor * (1.5 ** (retries - 1))
                        time.sleep(sleep_time)

        # Import tqdm here to keep standard library fast
        from tqdm import tqdm

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {executor.submit(fetch_segment, seg): seg for seg in segments}
            
            iterable = as_completed(futures)
            if progress_cb is None:
                iterable = tqdm(
                    iterable,
                    total=len(segments),
                    desc="Downloading segments",
                    unit="seg"
                )
                
            for future in iterable:
                idx, data = future.result()
                raw_payloads[idx] = data
                if progress_cb:
                    progress_cb(len(raw_payloads), len(segments))

        return raw_payloads
