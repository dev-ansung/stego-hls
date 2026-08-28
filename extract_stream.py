import subprocess
import json
import os
import re
import urllib.parse
import httpx

applescript = """
tell application "Google Chrome"
	set found to false
	set winIdx to 1
	set tabIdx to 1
	set wList to windows
	repeat with w in wList
		set idx to 1
		set tList to tabs of w
		repeat with t in tList
			if URL of t contains "sextb.net/mizd-420-rm" then
				set winIdx to id of w
				set tabIdx to idx
				set found to true
				exit repeat
			end if
			set idx to idx + 1
		end repeat
		if found then exit repeat
	end repeat
	
	if found then
		tell window id winIdx
			tell tab tabIdx
				execute javascript "
					(function() {
						var urls = [];
						var iframes = document.getElementsByTagName('iframe');
						for (var i = 0; i < iframes.length; i++) {
							if (iframes[i].src) urls.push(iframes[i].src);
						}
						var videos = document.getElementsByTagName('video');
						for (var i = 0; i < videos.length; i++) {
							if (videos[i].src) urls.push(videos[i].src);
							var sources = videos[i].getElementsByTagName('source');
							for (var j = 0; j < sources.length; j++) {
								if (sources[j].src) urls.push(sources[j].src);
							}
						}
						return urls.join('\\\\n');
					})()
				"
			end tell
		end tell
	else
		return "Tab not found"
	end if
end tell
"""

def get_mp4_duration(url: str) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "csv=p=0", url
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        return float(res.stdout.strip())
    raise ValueError(f"ffprobe failed: {res.stderr}")

from m3u8_downloader import process_playlist, download_and_extract_segment

def main():
    print("Executing AppleScript to extract video source from Chrome tab...")
    res = subprocess.run(["osascript", "-e", applescript], capture_output=True, text=True)
    
    url = None
    if "execution error" in res.stderr or "JavaScript through AppleScript is turned off" in res.stderr:
        print("\n[!] Chrome JavaScript execution via AppleScript is currently disabled.")
        print("To enable it, go to Google Chrome's menu bar and toggle:")
        print("   View > Developer > Allow JavaScript from Apple Events")
        print("\nAlternatively, copy the media streaming link (.mp4 or .m3u8) from your extension and paste it below:")
        url = input("Streaming Link: ").strip()
    else:
        output = res.stdout.strip()
        if "Tab not found" in output or not output:
            print("[!] Could not find active 'sextb.net/mizd-420-rm' tab in Chrome.")
            url = input("Please paste the copied streaming link manually: ").strip()
        else:
            urls = [line.strip() for line in output.split('\n') if line.strip()]
            print(f"Extracted URLs from Chrome tab: {urls}")
            for u in urls:
                if "cloudatacdn" in u or "dood" in u or "stream" in u or "video" in u:
                    url = u
                    break
            if not url and urls:
                url = urls[0]
                
            if not url:
                url = input("Could not find media link in DOM. Please paste manually: ").strip()

    if not url:
        print("No URL provided. Exiting.")
        return

    print(f"\nTarget URL to download: {url}")
    referer = "https://supjav.com/"
    os.makedirs("download", exist_ok=True)
    output_path = "download/mizd-420-rm_clip.mp4"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": referer
    }
    
    is_mp4 = False
    print("Probing stream format...")
    try:
        with httpx.Client(headers=headers, follow_redirects=True, timeout=10.0) as client:
            with client.stream("GET", url) as r:
                content_type = r.headers.get("content-type", "").lower()
                if "video/" in content_type or url.endswith(".mp4") or "mp4" in content_type:
                    is_mp4 = True
                    print(f"Detected direct video format: {content_type}")
    except Exception as e:
        print(f"Format probe warning: {e}")

    if is_mp4:
        print("Processing direct video link...")
        try:
            duration = get_mp4_duration(url)
            mid = duration / 2
            start = max(0.0, mid - 5.0)
            end = mid + 5.0
            print(f"Duration: {duration:.2f}s, clipping range: {start:.2f}s - {end:.2f}s")
            
            cmd = [
                "ffmpeg", "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
                "-i", url, "-c", "copy", output_path
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                print(f"Success! Saved clip to {output_path}")
            else:
                print(f"Failed direct video clip: {res.stderr}")
        except Exception as e:
            print(f"Failed direct video download: {e}")
        return

    try:
        print("Parsing HLS playlist...")
        sub_url, segments = process_playlist(url, referer)
        print(f"HLS stream has {len(segments)} segments.")
        
        segment_timeline = []
        cum_time = 0.0
        for s_idx, (seg_url, dur) in enumerate(segments):
            segment_timeline.append({
                "idx": s_idx, "url": seg_url, "duration": dur, "start": cum_time, "end": cum_time + dur
            })
            cum_time += dur
            
        duration = cum_time
        mid = duration / 2
        start = max(0.0, mid - 5.0)
        end = mid + 5.0
        print(f"Total HLS Duration: {duration:.2f}s, clipping range: {start:.2f}s - {end:.2f}s")
        
        overlapping = [seg for seg in segment_timeline if seg["start"] < end and seg["end"] > start]
        if not overlapping:
            print("No overlapping segments found.")
            return
            
        first_seg_idx = overlapping[0]["idx"]
        first_seg_start = overlapping[0]["start"]
        rel_start = start - first_seg_start
        rel_end = end - first_seg_start
        
        print("Attempting steganographic segment download & extraction...")
        download_headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        stego_success = True
        payloads = {}
        with httpx.Client(headers=download_headers, follow_redirects=True, timeout=60.0) as client:
            for seg in overlapping:
                try:
                    _, ts_bytes = download_and_extract_segment(seg["idx"], seg["url"], client, referer)
                    payloads[seg["idx"]] = ts_bytes
                except Exception as e:
                    print(f"Stego extraction failed on segment: {e}")
                    stego_success = False
                    break
                    
        if stego_success:
            temp_ts = "download/temp_extract.ts"
            with open(temp_ts, "wb") as f:
                for s_idx in sorted(payloads.keys()):
                    f.write(payloads[s_idx])
            
            cmd = ["ffmpeg", "-y", "-ss", f"{rel_start:.3f}", "-to", f"{rel_end:.3f}", "-i", temp_ts, "-c", "copy", output_path]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if os.path.exists(temp_ts):
                os.remove(temp_ts)
                
            if res.returncode == 0:
                print(f"Success! Saved clip to {output_path}")
                return
            
        print("Running direct HLS download fallback...")
        cmd = [
            "ffmpeg", "-y", "-headers", f"Referer: {referer}\r\nUser-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36\r\n",
            "-allowed_extensions", "ALL",
            "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
            "-i", sub_url, "-c", "copy", output_path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            print(f"Success! Saved HLS clip to {output_path}")
        else:
            print(f"Direct HLS download failed: {res.stderr}")
            
    except Exception as e:
        print(f"Failed HLS processing: {e}")

if __name__ == "__main__":
    main()
