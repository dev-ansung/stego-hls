from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from stego_hls.cli import parse_timestamp, run_batch


def test_parse_timestamp() -> None:
    # MM:SS format
    assert parse_timestamp("08:00") == 480.0
    assert parse_timestamp("44:00") == 2640.0
    
    # HH:MM:SS format
    assert parse_timestamp("1:03:00") == 3780.0
    assert parse_timestamp("2:18:00") == 8280.0
    
    # Raw seconds format
    assert parse_timestamp("12") == 12.0
    
    # Invalid formats
    with pytest.raises(ValueError):
        parse_timestamp("abc")


@patch("stego_hls.cli.HlsClipper")
def test_run_batch_single_task(mock_clipper_class: MagicMock) -> None:
    # Arrange
    mock_clipper = MagicMock()
    mock_clipper_class.return_value = mock_clipper
    
    tasks = [
        {
            "url": "https://example-cdn.com/my-video.m3u8",
            "referer": "https://example-referrer.com/page.html",
            "output": "download/custom_clip.mp4",
            "time": "08:00-12:00"
        }
    ]

    # Act
    run_batch(tasks, parallel=4, transcode=False)

    # Assert
    assert mock_clipper.clip.called is True
    mock_clipper.clip.assert_called_once_with(
        "https://example-cdn.com/my-video.m3u8",
        start="480.0",
        end="720.0",
        output_path=Path("download/custom_clip.mp4"),
        headers={
            "Referer": "https://example-referrer.com/page.html",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
    )


@patch("stego_hls.cli.HlsClipper")
def test_run_batch_multiple_times(mock_clipper_class: MagicMock) -> None:
    # Arrange
    mock_clipper = MagicMock()
    mock_clipper_class.return_value = mock_clipper
    
    tasks = [
        {
            "url": "https://example-cdn.com/my-video.m3u8",
            "time": ["01:00-02:00", "05:00"]
        }
    ]

    # Act
    run_batch(tasks, parallel=4, transcode=False)

    # Assert
    assert mock_clipper.clip.call_count == 2
