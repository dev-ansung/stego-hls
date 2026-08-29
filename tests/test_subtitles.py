from stego_hls.subtitles import format_srt_time, parse_srt_time, shift_srt_content


def test_parse_srt_time() -> None:
    assert parse_srt_time("00:01:20,000") == 80.0
    assert parse_srt_time("00:01:20.500") == 80.5
    assert parse_srt_time("01:00:00") == 3600.0
    assert parse_srt_time("05:00") == 300.0
    assert parse_srt_time("10") == 10.0


def test_format_srt_time() -> None:
    assert format_srt_time(80.0) == "00:01:20,000"
    assert format_srt_time(80.5) == "00:01:20,500"
    assert format_srt_time(3661.123) == "01:01:01,123"
    assert format_srt_time(-5.0) == "00:00:00,000"


def test_shift_srt_content() -> None:
    content = """1
00:00:02,000 --> 00:00:05,000
First sub

2
00:00:06,500 --> 00:00:10,000
Second sub
"""
    
    # Shift by 3s, clamp at duration 5s (range 3.0 to 8.0)
    shifted = shift_srt_content(content, start_sec=3.0, end_sec=8.0)
    
    expected = """1
00:00:00,000 --> 00:00:02,000
First sub

2
00:00:03,500 --> 00:00:05,000
Second sub
"""
    assert shifted.strip() == expected.strip()
