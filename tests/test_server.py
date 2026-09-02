from unittest.mock import MagicMock

from stego_hls.server import HlsProxyServer
from stego_hls.subtitles import srt_to_vtt


def test_srt_to_vtt_conversion():
    srt_text = """1
00:00:01,000 --> 00:00:04,500
Hello World!

2
00:00:05,200 --> 00:00:08,100
Second subtitle line.
"""
    vtt = srt_to_vtt(srt_text)
    assert vtt.startswith("WEBVTT\n\n")
    assert "00:00:01.000 --> 00:00:04.500" in vtt
    assert "00:00:05.200 --> 00:00:08.100" in vtt
    assert "Hello World!" in vtt
    assert "Second subtitle line." in vtt


def test_hls_proxy_manifest_rewriting():
    proxy = HlsProxyServer("https://example.com/master.m3u8", port=8000)

    # Mock timeline
    mock_seg0 = MagicMock(index=0, duration=4.0, url="https://example.com/seg0.png")
    mock_seg1 = MagicMock(index=1, duration=4.0, url="https://example.com/seg1.png")
    mock_timeline = MagicMock(segments=[mock_seg0, mock_seg1], target_duration=4)

    proxy.timeline = mock_timeline

    manifest = proxy.get_rewritten_manifest()
    assert "#EXTM3U" in manifest
    assert "#EXTINF:4.000000," in manifest
    assert "/segment/0.ts" in manifest
    assert "/segment/1.ts" in manifest
    assert "#EXT-X-ENDLIST" in manifest
