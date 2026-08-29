import subprocess
from typing import Protocol

type DecodedPayloads = dict[int, bytes]


class Muxer(Protocol):
    def concatenate_and_clip(self, 
                             payloads: DecodedPayloads, 
                             *, 
                             relative_start: float, 
                             relative_end: float, 
                             output_path: str) -> None:
        """Concatenates the payloads and trims them to output_path."""
        ...


class FfmpegMuxer(Muxer):
    def __init__(self, *, transcode: bool = False) -> None:
        self.transcode = transcode

    def concatenate_and_clip(self, 
                             payloads: DecodedPayloads, 
                             *, 
                             relative_start: float, 
                             relative_end: float, 
                             output_path: str) -> None:
        """Pipes TS payload bytes directly into FFmpeg's stdin to output an MP4."""
        cmd = [
            "ffmpeg", "-y", 
            "-i", "pipe:0",
            "-ss", f"{relative_start:.3f}", 
            "-to", f"{relative_end:.3f}"
        ]
        
        if self.transcode:
            cmd.extend(["-c:v", "libx264", "-c:a", "aac"])
        else:
            cmd.extend(["-c", "copy"])
            
        cmd.append(output_path)
        
        with subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=None) as process:
            try:
                for index in sorted(payloads.keys()):
                    process.stdin.write(payloads[index])
                process.stdin.close()
                rc = process.wait()
            except (BrokenPipeError, ConnectionResetError):
                rc = process.wait()
            except Exception as e:  # noqa: BLE001
                process.kill()
                raise RuntimeError(f"FFmpeg stream remuxing failed: {e}")
                
            if rc != 0:
                raise RuntimeError(f"FFmpeg stream remuxing failed (exit {rc}). See FFmpeg logs above.")
