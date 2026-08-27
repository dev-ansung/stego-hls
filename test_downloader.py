import unittest
import os
import sys

# Add current directory to path
sys.path.append(os.path.dirname(__file__))

import m3u8_downloader

class TestM3U8Downloader(unittest.TestCase):

    def test_parse_timestamp(self):
        # Test MM:SS format
        self.assertEqual(m3u8_downloader.parse_timestamp("08:00"), 480.0)
        self.assertEqual(m3u8_downloader.parse_timestamp("44:00"), 2640.0)
        
        # Test HH:MM:SS format
        self.assertEqual(m3u8_downloader.parse_timestamp("1:03:00"), 3780.0)
        self.assertEqual(m3u8_downloader.parse_timestamp("2:18:00"), 8280.0)
        
        # Test invalid formats
        with self.assertRaises(ValueError):
            m3u8_downloader.parse_timestamp("abc")
        with self.assertRaises(ValueError):
            m3u8_downloader.parse_timestamp("12")

    def test_parse_input_text(self):
        input_text = """
        https://supjav.com/zh/452901.html
        https://cdn4.turboviplay.com/data3/6a8d6e45b0b5f/6a8d6e45b0b5f.m3u8
        ABW-204
            08:00-12:00
            2:18:00
        """
        referer, master_url, prefix, ranges = m3u8_downloader.parse_input_text(input_text)
        
        self.assertEqual(referer, "https://supjav.com/zh/452901.html")
        self.assertEqual(master_url, "https://cdn4.turboviplay.com/data3/6a8d6e45b0b5f/6a8d6e45b0b5f.m3u8")
        self.assertEqual(prefix, "ABW-204")
        
        self.assertEqual(len(ranges), 2)
        # Range 1: 08:00-12:00
        self.assertEqual(ranges[0][0], 480.0)
        self.assertEqual(ranges[0][1], 720.0)
        self.assertEqual(ranges[0][2], "08:00-12:00")
        
        # Range 2: 2:18:00 (open range)
        self.assertEqual(ranges[1][0], 8280.0)
        self.assertEqual(ranges[1][1], None)
        self.assertEqual(ranges[1][2], "2:18:00")

    def test_find_ts_start_offset(self):
        # Build mock segment data:
        # Mock PNG signature and chunks up to IEND
        png_header = b"\x89PNG\r\n\x1a\n"
        ihdr_chunk = b"\x00\x00\x00\x0dIHDR\x00\x00\x01\xf4\x00\x00\x01\xf4\x08\x02\x00\x00\x00\x44\xb4\x48\xdd"
        idat_chunk = b"\x00\x00\x02\xedIDAT\x78\xda\xed\xc1\x01\x01"
        iend_chunk = b"\x00\x00\x00\x00IEND\xae\x42\x60\x82"
        
        # Padding
        padding = b"\xff" * 128
        
        # Correct TS sync pattern starting with 0x47, repeating at 188-byte intervals
        # Packet 1
        ts_packet_1 = b"\x47" + b"\x00" * 187
        # Packet 2
        ts_packet_2 = b"\x47" + b"\x00" * 187
        # Packet 3
        ts_packet_3 = b"\x47" + b"\x00" * 187
        
        mock_data = png_header + ihdr_chunk + idat_chunk + iend_chunk + padding + ts_packet_1 + ts_packet_2 + ts_packet_3
        
        # Expectation: Start offset points exactly to start of ts_packet_1
        expected_offset = len(png_header + ihdr_chunk + idat_chunk + iend_chunk + padding)
        actual_offset = m3u8_downloader.find_ts_start_offset(mock_data)
        
        self.assertEqual(actual_offset, expected_offset)
        
        # Test case where no TS is found
        invalid_data = b"This is just some random text file."
        self.assertEqual(m3u8_downloader.find_ts_start_offset(invalid_data), -1)

if __name__ == '__main__':
    unittest.main()
