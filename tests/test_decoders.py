import pytest
from stego_hls.decoders import PassthroughDecoder, StegoDecoder


def test_passthrough_decoder() -> None:
    decoder = PassthroughDecoder()
    data = b"my_plain_ts_packets"
    assert decoder.decode(data) == data


def test_stego_decoder_valid_offset() -> None:
    decoder = StegoDecoder()
    
    # Construct mock PNG image bytes with target trailing TS packets
    # Packets must start with sync byte 0x47, spaced by 188 bytes
    mock_image_header = b"PNG_HEADER_DATA_IEND\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    
    # First sync packet
    packet1 = b"\x47" + b"\x00" * 187
    # Second sync packet
    packet2 = b"\x47" + b"\x00" * 187
    # Third sync packet
    packet3 = b"\x47" + b"\x00" * 187
    
    full_payload = mock_image_header + packet1 + packet2 + packet3
    
    decoded = decoder.decode(full_payload)
    assert decoded.startswith(b"\x47")
    assert len(decoded) == 188 * 3


def test_stego_decoder_invalid_packets() -> None:
    decoder = StegoDecoder()
    
    # Image content without sync bytes
    bad_payload = b"PNG_HEADER_DATA_IEND\x00\x00\x00\x00_some_random_payload_bytes"
    
    with pytest.raises(ValueError, match="MPEG-TS sync pattern not found"):
        decoder.decode(bad_payload)
