import pytest

from stego_hls.cli import parse_input_text, parse_timestamp


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


def test_parse_input_text() -> None:
    input_text = """
    https://example-referrer.com/page.html
    https://example-cdn.com/stream/playlist.m3u8
    example-video
        08:00-12:00
        2:18:00
    """
    referer, master_url, prefix, ranges = parse_input_text(input_text)
    
    assert referer == "https://example-referrer.com/page.html"
    assert master_url == "https://example-cdn.com/stream/playlist.m3u8"
    assert prefix == "example-video"
    
    assert len(ranges) == 2
    
    # Range 1: 08:00-12:00
    assert ranges[0][0] == 480.0
    assert ranges[0][1] == 720.0
    assert ranges[0][2] == "08:00-12:00"
    
    # Range 2: 2:18:00 (open range)
    assert ranges[1][0] == 8280.0
    assert ranges[1][1] is None
    assert ranges[1][2] == "2:18:00"
