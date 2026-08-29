import shutil
from pathlib import Path
from typing import Protocol


class SegmentCache(Protocol):
    def get(self, stream_hash: str, index: int) -> bytes | None:
        """Retrieves cached segment bytes if they exist."""
        ...

    def set(self, stream_hash: str, index: int, data: bytes) -> None:
        """Saves segment bytes to the cache."""
        ...

    def clear(self, stream_hash: str) -> None:
        """Removes all cached segments for a stream."""
        ...


class FileSegmentCache(SegmentCache):
    def __init__(self, cache_dir: str | Path = ".stego_cache") -> None:
        self.cache_dir = Path(cache_dir)

    def _get_path(self, stream_hash: str, index: int) -> Path:
        return self.cache_dir / stream_hash / f"{index}.ts"

    def get(self, stream_hash: str, index: int) -> bytes | None:
        path = self._get_path(stream_hash, index)
        if path.exists() and path.stat().st_size > 0:
            try:
                return path.read_bytes()
            except OSError:
                return None
        return None

    def set(self, stream_hash: str, index: int, data: bytes) -> None:
        path = self._get_path(stream_hash, index)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except OSError:
            pass

    def clear(self, stream_hash: str) -> None:
        stream_dir = self.cache_dir / stream_hash
        if stream_dir.exists():
            try:
                shutil.rmtree(stream_dir)
            except OSError:
                pass
            
        # Clean up root cache directory if it's completely empty
        if self.cache_dir.exists():
            try:
                if not any(self.cache_dir.iterdir()):
                    self.cache_dir.rmdir()
            except OSError:
                pass


class NullSegmentCache(SegmentCache):
    def get(self, stream_hash: str, index: int) -> bytes | None:
        return None

    def set(self, stream_hash: str, index: int, data: bytes) -> None:
        pass

    def clear(self, stream_hash: str) -> None:
        pass
