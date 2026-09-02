from unittest.mock import patch

from stego_hls.wizard import prompt_input


def test_prompt_input_with_default():
    with patch("builtins.input", return_value=""):
        result = prompt_input("Enter test value", default="my_default")
        assert result == "my_default"


def test_prompt_input_with_quotes():
    with patch("builtins.input", return_value="'/path/to/my video.srt'"):
        result = prompt_input("Enter SRT")
        assert result == "/path/to/my video.srt"


def test_prompt_input_with_escaped_spaces():
    with patch("builtins.input", return_value="/path/to/my\\ video.srt"):
        result = prompt_input("Enter SRT")
        assert result == "/path/to/my video.srt"
