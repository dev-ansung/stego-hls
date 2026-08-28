import re
import urllib.parse
from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class Segment:
    index: int
    url: str
    duration: float
    start_time: float
    end_time: float


class Timeline:
    def __init__(self, segments: list[Segment], /) -> None:
        self.segments = segments
        self.total_duration = sum(seg.duration for seg in segments)

    def get_overlapping_segments(self, *, start_sec: float, end_sec: float) -> list[Segment]:
        """Returns all HLS segments that overlap with the target time range."""
        return [
            seg for seg in self.segments
            if seg.start_time < end_sec and seg.end_time > start_sec
        ]


class PlaylistParser:
    @staticmethod
    def parse_manifest(manifest_content: str, *, base_url: str) -> Timeline:
        """Parses raw manifest content to construct the Timeline segments list."""
        lines = [line.strip() for line in manifest_content.split("\n") if line.strip()]
        segments: list[Segment] = []
        cum_time = 0.0
        current_duration = 0.0
        
        segment_index = 0
        for line in lines:
            if line.startswith("#EXTINF:"):
                dur_match = re.match(r"#EXTINF:([0-9.]+)", line)
                if dur_match:
                    current_duration = float(dur_match.group(1))
            elif line and not line.startswith("#"):
                resolved_url = urllib.parse.urljoin(base_url, line)
                segments.append(
                    Segment(
                        index=segment_index,
                        url=resolved_url,
                        duration=current_duration,
                        start_time=cum_time,
                        end_time=cum_time + current_duration
                    )
                )
                cum_time += current_duration
                segment_index += 1
                
        return Timeline(segments)

    @staticmethod
    def resolve_sub_playlist(master_content: str, *, master_url: str) -> str:
        """
        Locates the sub-playlist URL from the master playlist content.
        Falls back to returning the master URL if the manifest is already a media playlist.
        """
        lines = [line.strip() for line in master_content.split("\n") if line.strip()]
        sub_playlists: list[str] = []
        
        for i, line in enumerate(lines):
            if line.startswith("#EXT-X-STREAM-INF") and i + 1 < len(lines):
                next_line = lines[i+1]
                if not next_line.startswith("#"):
                    sub_playlists.append(urllib.parse.urljoin(master_url, next_line))
                    
        if not sub_playlists:
            if "#EXTINF" in master_content:
                return master_url
            for line in lines:
                if not line.startswith("#") and (".m3u8" in line or ".txt" in line or "playlist" in line):
                    sub_playlists.append(urllib.parse.urljoin(master_url, line))
                    
            if not sub_playlists:
                raise ValueError("No sub-playlists found in master playlist.")
                
        return sub_playlists[-1]
