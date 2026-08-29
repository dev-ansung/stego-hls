from unittest.mock import MagicMock

import httpx
import pytest

from stego_hls.downloader import ParallelDownloader
from stego_hls.playlist import Segment


class MemorySegmentCache:
    """A clean memory-based SegmentCache stub for testing caching logic without hitting disk."""
    def __init__(self) -> None:
        self.store: dict[str, dict[int, bytes]] = {}

    def get(self, stream_hash: str, index: int) -> bytes | None:
        return self.store.get(stream_hash, {}).get(index)

    def set(self, stream_hash: str, index: int, data: bytes) -> None:
        self.store.setdefault(stream_hash, {})[index] = data

    def clear(self, stream_hash: str) -> None:
        if stream_hash in self.store:
            del self.store[stream_hash]


def test_downloader_cache_hit() -> None:
    # Arrange: Setup cache containing segment data
    cache = MemorySegmentCache()
    stream_hash = "test_hash"
    cache.set(stream_hash, index=1, data=b"cached_segment_bytes")

    mock_client = MagicMock()  # Client is not called on cache hit
    downloader = ParallelDownloader(workers=1, client=mock_client, cache=cache)
    
    segments = [Segment(index=1, duration=5.0, url="https://example.com/1.ts", start_time=0.0, end_time=5.0)]

    # Act
    results = downloader.download(segments, headers={}, stream_hash=stream_hash)

    # Assert
    assert results == {1: b"cached_segment_bytes"}
    assert mock_client.get.called is False  # Verify no network requests occurred


def test_downloader_cache_miss() -> None:
    # Arrange: Cache is empty
    cache = MemorySegmentCache()
    stream_hash = "test_hash"

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = b"downloaded_bytes"
    mock_client.get.return_value = mock_response

    downloader = ParallelDownloader(workers=1, client=mock_client, cache=cache)
    segments = [Segment(index=1, duration=5.0, url="https://example.com/1.ts", start_time=0.0, end_time=5.0)]

    # Act
    results = downloader.download(segments, headers={}, stream_hash=stream_hash)

    # Assert
    assert results == {1: b"downloaded_bytes"}
    assert mock_client.get.called is True
    # Verify cache was updated
    assert cache.get(stream_hash, 1) == b"downloaded_bytes"


def test_downloader_retry_success() -> None:
    # Arrange
    cache = MemorySegmentCache()
    stream_hash = "test_hash"

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = b"success_bytes"

    # Fail twice (raise HTTPError), succeed on the 3rd call
    mock_client.get.side_effect = [
        httpx.HTTPStatusError("503 Service Unavailable", request=MagicMock(), response=MagicMock()),
        httpx.ConnectError("Connection timed out"),
        mock_response
    ]

    # Set backoff_factor=0.0 to execute instantly in tests
    downloader = ParallelDownloader(workers=1, client=mock_client, cache=cache, max_retries=3, backoff_factor=0.0)
    segments = [Segment(index=1, duration=5.0, url="https://example.com/1.ts", start_time=0.0, end_time=5.0)]

    # Act
    results = downloader.download(segments, headers={}, stream_hash=stream_hash)

    # Assert
    assert results == {1: b"success_bytes"}
    assert mock_client.get.call_count == 3
    assert cache.get(stream_hash, 1) == b"success_bytes"


def test_downloader_retry_failure() -> None:
    # Arrange
    cache = MemorySegmentCache()
    stream_hash = "test_hash"

    mock_client = MagicMock()
    # Always fail
    mock_client.get.side_effect = httpx.ConnectError("Fatal network error")

    downloader = ParallelDownloader(workers=1, client=mock_client, cache=cache, max_retries=3, backoff_factor=0.0)
    segments = [Segment(index=1, duration=5.0, url="https://example.com/1.ts", start_time=0.0, end_time=5.0)]

    # Act & Assert: Should raise RuntimeError after 3 retries (total 4 attempts: 1 original + 3 retries)
    with pytest.raises(RuntimeError, match="Failed to download segment 1 after 3 retries"):
        downloader.download(segments, headers={}, stream_hash=stream_hash)

    assert mock_client.get.call_count == 4
