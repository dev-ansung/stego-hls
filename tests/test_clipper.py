from pathlib import Path
from unittest.mock import MagicMock, patch

from stego_hls.clipper import HlsClipper
from stego_hls.decoders import BaseDecoder

type DecodedPayloads = dict[int, bytes]


class MockMuxer:
    def __init__(self, *, transcode: bool = False) -> None:
        self.transcode = transcode
        self.called = False
        self.relative_start = 0.0
        self.relative_end = 0.0
        self.payloads: DecodedPayloads = {}

    @property
    def requires_keyframe_alignment(self) -> bool:
        return not self.transcode

    def concatenate_and_clip(self, 
                             payloads: DecodedPayloads, 
                             *, 
                             relative_start: float, 
                             relative_end: float, 
                             output_path: str) -> None:
        self.called = True
        self.payloads = payloads
        self.relative_start = relative_start
        self.relative_end = relative_end


class MockDecoder(BaseDecoder):
    def decode(self, raw_bytes: bytes, /) -> bytes:
        return raw_bytes  # Passthrough mock


@patch("httpx.Client")
def test_clipper_pipeline_execution(mock_client_class: MagicMock) -> None:
    # Arrange: Setup mock HTTP response for HLS playlist manifest
    mock_client = MagicMock()
    mock_client_class.return_value.__enter__.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.text = """
#EXTM3U
#EXT-X-VERSION:3
#EXTINF:5.000,
0.ts
#EXTINF:5.000,
1.ts
    """
    mock_client.get.return_value = mock_response

    # Setup mock Downloader
    mock_downloader = MagicMock()
    mock_downloader.download.return_value = {
        0: b"segment_0_raw",
        1: b"segment_1_raw"
    }
    
    mock_muxer = MockMuxer(transcode=False)
    mock_decoder = MockDecoder()

    # Act: Instantiate Clipper and run clipping
    clipper = HlsClipper(
        downloader=mock_downloader,
        decoder=mock_decoder,
        muxer=mock_muxer
    )
    
    final_path = clipper.clip(
        "https://example.com/master.m3u8",
        start="2.0",
        end="8.0",
        output_prefix="download/out.mp4"
    )

    # Assertions
    assert mock_muxer.called is True
    # Copy mode: aligned to segment start (0.0)
    assert mock_muxer.relative_start == 0.0
    assert mock_muxer.relative_end == 8.0
    assert mock_muxer.payloads == {0: b"segment_0_raw", 1: b"segment_1_raw"}
    assert final_path == Path("download/out.mp4")


@patch("httpx.Client")
def test_clipper_pipeline_execution_transcode(mock_client_class: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_class.return_value.__enter__.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.text = """
#EXTM3U
#EXT-X-VERSION:3
#EXTINF:5.000,
0.ts
#EXTINF:5.000,
1.ts
    """
    mock_client.get.return_value = mock_response

    mock_downloader = MagicMock()
    mock_downloader.download.return_value = {
        0: b"segment_0_raw",
        1: b"segment_1_raw"
    }
    
    mock_muxer = MockMuxer(transcode=True)
    mock_decoder = MockDecoder()

    clipper = HlsClipper(
        downloader=mock_downloader,
        decoder=mock_decoder,
        muxer=mock_muxer
    )
    
    final_path = clipper.clip(
        "https://example.com/master.m3u8",
        start="2.0",
        end="8.0",
        output_prefix="download/out.mp4"
    )

    # Transcode mode: exact start offset (2.0)
    assert mock_muxer.relative_start == 2.0
    assert final_path == Path("download/out.mp4")


@patch("httpx.Client")
def test_clipper_pipeline_execution_no_align(mock_client_class: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_class.return_value.__enter__.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.text = """
#EXTM3U
#EXT-X-VERSION:3
#EXTINF:5.000,
0.ts
#EXTINF:5.000,
1.ts
    """
    mock_client.get.return_value = mock_response

    mock_downloader = MagicMock()
    mock_downloader.download.return_value = {
        0: b"segment_0_raw",
        1: b"segment_1_raw"
    }
    
    mock_muxer = MockMuxer(transcode=False)
    mock_decoder = MockDecoder()

    clipper = HlsClipper(
        downloader=mock_downloader,
        decoder=mock_decoder,
        muxer=mock_muxer
    )
    
    final_path = clipper.clip(
        "https://example.com/master.m3u8",
        start="2.0",
        end="8.0",
        output_prefix="download/out.mp4",
        align_bounds=False
    )

    # Copy mode with align_bounds=False: exact start offset (2.0)
    assert mock_muxer.relative_start == 2.0
    assert final_path == Path("download/out.mp4")


def test_resolve_output_path() -> None:
    # Arrange
    clipper = HlsClipper(
        downloader=MagicMock(),
        decoder=MagicMock(),
        muxer=MagicMock()
    )

    # Case 1: Explicit .mp4 path
    prefix = Path("download/my_video.mp4")
    resolved = clipper._resolve_output_path(prefix, start_sec=3030.0, end_sec=3587.0, end_original="59:47")
    assert resolved == Path("download/my_video.mp4")

    # Case 2: Folder prefix with range
    prefix = Path("download/my_prefix")
    resolved = clipper._resolve_output_path(prefix, start_sec=480.0, end_sec=720.0, end_original="12:00")
    assert resolved == Path("download/my_prefix.08_00-12_00.mp4")

    # Case 3: Folder prefix with single timestamp
    prefix = Path("download/my_prefix")
    resolved = clipper._resolve_output_path(prefix, start_sec=480.0, end_sec=99999999.0, end_original="99999999.0")
    assert resolved == Path("download/my_prefix.08_00.mp4")
