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
    
    clipper.clip(
        "https://example.com/master.m3u8",
        start="2.0",
        end="8.0",
        output_path="download/out.mp4"
    )

    # Assertions
    assert mock_muxer.called is True
    # Copy mode: aligned to segment start (0.0)
    assert mock_muxer.relative_start == 0.0
    assert mock_muxer.relative_end == 8.0
    assert mock_muxer.payloads == {0: b"segment_0_raw", 1: b"segment_1_raw"}


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
    
    clipper.clip(
        "https://example.com/master.m3u8",
        start="2.0",
        end="8.0",
        output_path="download/out.mp4"
    )

    # Transcode mode: exact start offset (2.0)
    assert mock_muxer.relative_start == 2.0
