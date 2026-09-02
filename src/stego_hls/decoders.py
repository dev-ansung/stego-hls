from abc import ABC, abstractmethod


class BaseDecoder(ABC):
    @abstractmethod
    def decode(self, raw_bytes: bytes, /) -> bytes:
        """Decode raw segment bytes into clean Transport Stream (.ts) payload."""


class PassthroughDecoder(BaseDecoder):
    def decode(self, raw_bytes: bytes, /) -> bytes:
        return raw_bytes


class StegoDecoder(BaseDecoder):
    MPEG_TS_PACKET_SIZE = 188
    SYNC_BYTE = 0x47

    def decode(self, raw_bytes: bytes, /) -> bytes:
        """Strips steganographic image frames and isolates the Transport Stream bytes."""
        iend_idx = raw_bytes.find(b"IEND")
        search_start = 0 if iend_idx == -1 else iend_idx + 12
        sub_data = raw_bytes[search_start:]
        
        for offset in range(len(sub_data) - self.MPEG_TS_PACKET_SIZE * 2):
            if (sub_data[offset] == self.SYNC_BYTE and
                sub_data[offset + self.MPEG_TS_PACKET_SIZE] == self.SYNC_BYTE and
                sub_data[offset + self.MPEG_TS_PACKET_SIZE * 2] == self.SYNC_BYTE):
                return sub_data[offset:]
                
        raise ValueError("MPEG-TS sync pattern not found in segment payload.")
