from pathlib import Path


def parse_srt_time(time_str: str) -> float:
    """Parses an SRT timestamp string (HH:MM:SS,mmm or HH:MM:SS.mmm) to float seconds."""
    time_str = time_str.replace(',', '.')
    parts = time_str.split(':')
    if len(parts) == 3:
        h, m, s = parts[0], parts[1], parts[2]
        return float(h) * 3600 + float(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts[0], parts[1]
        return float(m) * 60 + float(s)
    else:
        return float(parts[0])


def format_srt_time(seconds: float) -> str:
    """Formats float seconds to standard SRT timestamp format: HH:MM:SS,mmm."""
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = round((seconds - int(seconds)) * 1000)
    if ms >= 1000:
        ms = 999
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def shift_srt_content(content: str, start_sec: float, end_sec: float) -> str:
    """Shifts subtitles backward by start_sec and filters/clips events to fit within [0, end_sec - start_sec]."""
    content = content.replace("\r\n", "\n").strip()
    if not content:
        return ""
        
    blocks = content.split("\n\n")
    shifted = []
    counter = 1
    duration = end_sec - start_sec
    
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 2:
            continue
        try:
            time_line = lines[1]
            if "-->" not in time_line:
                time_line = lines[0]
                text_start_idx = 1
            else:
                text_start_idx = 2
                
            start_str, end_str = time_line.split("-->")
            start = parse_srt_time(start_str.strip())
            end = parse_srt_time(end_str.strip())
            
            new_start = start - start_sec
            new_end = end - start_sec
            
            # Skip if subtitles lie entirely outside the clipped duration
            if new_end <= 0 or new_start >= duration:
                continue
                
            # Clamp limits
            if new_start < 0:
                new_start = 0.0
            new_end = min(new_end, duration)
                
            text = lines[text_start_idx:]
            shifted.append(
                f"{counter}\n{format_srt_time(new_start)} --> {format_srt_time(new_end)}\n" + "\n".join(text)
            )
            counter += 1
        except (ValueError, IndexError):
            continue
            
    return "\n\n".join(shifted) + "\n"


def process_srt_file(input_path: str | Path, start_sec: float, end_sec: float, output_path: str | Path) -> None:
    """Reads input SRT file, shifts timings, and writes output SRT file."""
    with open(input_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
        
    shifted_content = shift_srt_content(content, start_sec, end_sec)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(shifted_content)


def srt_to_vtt(content: str) -> str:
    """Converts standard SRT subtitle text into WebVTT format."""
    content = content.replace("\r\n", "\n").strip()
    if not content:
        return "WEBVTT\n\n"
        
    blocks = content.split("\n\n")
    vtt_blocks = []
    
    for block in blocks:
        lines = block.strip().split("\n")
        if not lines:
            continue
        vtt_lines = []
        for line in lines:
            if "-->" in line:
                vtt_lines.append(line.replace(",", "."))
            else:
                vtt_lines.append(line)
        vtt_blocks.append("\n".join(vtt_lines))
        
    return "WEBVTT\n\n" + "\n\n".join(vtt_blocks) + "\n"

