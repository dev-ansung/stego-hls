from pathlib import Path

from stego_hls.cache import FileSegmentCache


def test_file_segment_cache_lifecycle(tmp_path: Path) -> None:
    # Arrange
    cache = FileSegmentCache(cache_dir=tmp_path)
    stream_hash = "abc123xyz"
    index = 42
    data = b"segment_data_bytes"

    # 1. Assert get on empty cache returns None
    assert cache.get(stream_hash, index) is None

    # 2. Assert set writes file and get reads it back
    cache.set(stream_hash, index, data)
    
    expected_file = tmp_path / stream_hash / f"{index}.ts"
    assert expected_file.exists() is True
    assert expected_file.read_bytes() == data
    
    assert cache.get(stream_hash, index) == data

    # 3. Assert clear deletes the stream subdirectory
    cache.clear(stream_hash)
    assert expected_file.exists() is False
    assert (tmp_path / stream_hash).exists() is False
