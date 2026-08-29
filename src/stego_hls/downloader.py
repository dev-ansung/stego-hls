from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

from stego_hls.playlist import Segment

type ProgressCallback = Callable[[int, int], None]

class ParallelDownloader:
    def __init__(self, *, workers: int = 8, client: httpx.Client | None = None) -> None:
        self.workers = workers
        self.client = client or httpx.Client(follow_redirects=True, timeout=30.0)

    def download(self, 
                 segments: list[Segment], 
                 headers: dict[str, str], 
                 *, 
                 progress_cb: ProgressCallback | None = None) -> dict[int, bytes]:
        """Downloads segment bytes concurrently using the configured HTTP client."""
        raw_payloads: dict[int, bytes] = {}

        def fetch_segment(seg: Segment) -> tuple[int, bytes]:
            # Construct per-request headers to prevent Host header pollution on CDNs
            req_headers = {}
            if "User-Agent" in headers:
                req_headers["User-Agent"] = headers["User-Agent"]
            if "Referer" in headers and "googleusercontent.com" not in seg.url:
                req_headers["Referer"] = headers["Referer"]
                parsed_ref = urllib.parse.urlparse(headers["Referer"])
                req_headers["Origin"] = f"{parsed_ref.scheme}://{parsed_ref.netloc}"
                
            resp = self.client.get(seg.url, headers=req_headers if req_headers else None)
            resp.raise_for_status()
            return seg.index, resp.content

        # Import inside function to avoid circular references if any
        import urllib.parse

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
