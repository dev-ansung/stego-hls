from stego_hls.playlist import PlaylistParser, Segment, Timeline


def test_timeline_duration_calculation() -> None:
    segments = [
        Segment(index=0, url="0.ts", duration=5.0, start_time=0.0, end_time=5.0),
        Segment(index=1, url="1.ts", duration=3.5, start_time=5.0, end_time=8.5),
    ]
    timeline = Timeline(segments)
    assert timeline.total_duration == 8.5


def test_get_overlapping_segments() -> None:
    segments = [
        Segment(index=0, url="0.ts", duration=4.0, start_time=0.0, end_time=4.0),
        Segment(index=1, url="1.ts", duration=4.0, start_time=4.0, end_time=8.0),
        Segment(index=2, url="2.ts", duration=4.0, start_time=8.0, end_time=12.0),
    ]
    timeline = Timeline(segments)
    
    # Range completely inside segment 1
    overlapping = timeline.get_overlapping_segments(start_sec=5.0, end_sec=7.0)
    assert len(overlapping) == 1
    assert overlapping[0].index == 1

    # Range overlapping segments 1 and 2
    overlapping = timeline.get_overlapping_segments(start_sec=6.0, end_sec=10.0)
    assert len(overlapping) == 2
    assert overlapping[0].index == 1
    assert overlapping[1].index == 2

    # Range covering all segments
    overlapping = timeline.get_overlapping_segments(start_sec=1.0, end_sec=11.0)
    assert len(overlapping) == 3


def test_parse_manifest_simple() -> None:
    manifest = """
#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:5
#EXTINF:4.000,
segment_0.png
#EXTINF:5.200,
segment_1.png
    """
    timeline = PlaylistParser.parse_manifest(manifest, base_url="https://example.com/stream/")
    
    assert len(timeline.segments) == 2
    assert timeline.total_duration == 9.2
    
    seg0 = timeline.segments[0]
    assert seg0.index == 0
    assert seg0.url == "https://example.com/stream/segment_0.png"
    assert seg0.duration == 4.0
    assert seg0.start_time == 0.0
    assert seg0.end_time == 4.0
    
    seg1 = timeline.segments[1]
    assert seg1.index == 1
    assert seg1.url == "https://example.com/stream/segment_1.png"
    assert seg1.duration == 5.2
    assert seg1.start_time == 4.0
    assert seg1.end_time == 9.2


def test_resolve_sub_playlist_direct() -> None:
    master = """
#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=1500000,RESOLUTION=1280x720
sub_1280.m3u8
    """
    sub_url = PlaylistParser.resolve_sub_playlist(master, master_url="https://example.com/master.m3u8")
    assert sub_url == "https://example.com/sub_1280.m3u8"
