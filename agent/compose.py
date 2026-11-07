"""Compose: Pruna clips + brand typography + beat-synced cuts + music -> mp4.

Every scene is cut on the beat grid (4 beats per scene); the last scene holds until the music ends.
The headline is split at the scene's emphasis phrase: the lead-in in DM Sans bold (ink),
the emphasis on its own line in DM Serif italic (accent), both easing in from below.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "assets" / "fonts"
W, H, FPS = 1920, 1080, 30


def _split(title, emphasis):
    t, e = title.strip().rstrip("."), emphasis.strip().rstrip(".")
    i = t.lower().rfind(e.lower())
    if e and i > 0:
        return t[:i].rstrip(" ,—-"), t[i:]
    if ":" in t:  # "Detect: flag the risky columns" -> lead "Detect:", accent the action
        head, tail = t.split(":", 1)
        return head + ":", tail.strip()
    return t, ""


def _scene_filter(idx, dur, title, emphasis, ink, accent, tmp):
    lead, emph = _split(title, emphasis)
    (tmp / f"lead{idx}.txt").write_text(lead)
    (tmp / f"emph{idx}.txt").write_text(emph)
    ease = "min(1,t*3.5)"  # ~0.3 s ease-in
    rise = f"(1-{ease})*(1-{ease})*40"
    longest = max(len(lead), int(len(emph) * 1.1))
    big = 92 if longest < 24 else (76 if longest < 32 else 64)
    # each line sits on its own paper-white pill, so it reads on any keyframe
    pill = "box=1:boxcolor=white@0.82:boxborderw=22|34"
    f = (f"[{idx}:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS},"
         f"tpad=stop_mode=clone:stop_duration=5,trim=duration={dur},setpts=PTS-STARTPTS,"
         f"drawtext=fontfile={FONTS/'display-bold.ttf'}:textfile={tmp/f'lead{idx}.txt'}:{pill}:"
         f"fontsize={big}:fontcolor={ink}:x=(w-tw)/2:y='80+{rise}':alpha='{ease}'")
    if emph:
        f += (f",drawtext=fontfile={FONTS/'serif-italic.ttf'}:textfile={tmp/f'emph{idx}.txt'}:{pill}:"
              f"fontsize={int(big*1.2)}:fontcolor={accent}:x=(w-tw)/2:y='80+{big}+62+{rise}*1.4':"
              f"alpha='min(1,max(0,(t-0.12)*3.5))'")
    return f + f"[s{idx}]"


def _lum(hex_):
    r, g, b = (int(hex_.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _sat(hex_):
    c = [int(hex_.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    return max(c) - min(c)


def text_colours(palette):
    """Text sits on white pills, so ink = darkest brand colour, accent = most saturated colour that
    is still dark enough to read on white (dark brands put their light colour in slot 1)."""
    ink = min(palette, key=_lum)
    readable = [c for c in palette if _lum(c) < 0.45 and c != ink]
    accent = max(readable, key=_sat) if readable else ink
    return ink, accent


def compose(outline, clips, music, out, bpm=128, beats_per_scene=4, total=20.0):
    brand, scenes = outline["brand"], outline["scenes"]
    ink, accent = text_colours(brand["palette"])
    beat = 60 / bpm
    durs = [beats_per_scene * beat] * len(scenes)
    durs[-1] = total - sum(durs[:-1])
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        args = []
        for c in clips:
            args += ["-i", str(c)]
        args += ["-i", str(music)]
        parts = [_scene_filter(i, d, s["title"], s["emphasis"], ink, accent, tmp)
                 for i, (s, d) in enumerate(zip(scenes, durs))]
        n = len(scenes)
        parts.append("".join(f"[s{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0,"
                     f"fade=t=out:st={total-0.4}:d=0.4[v]")
        parts.append(f"[{n}:a]atrim=0:{total},afade=t=out:st={total-0.6}:d=0.6[a]")
        cmd = ["ffmpeg", "-y", "-loglevel", "error", *args,
               "-filter_complex", ";".join(parts), "-map", "[v]", "-map", "[a]",
               "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)]
        subprocess.run(cmd, check=True)
    return out


if __name__ == "__main__":
    outline = json.load(open(sys.argv[1]))
    clips = [l.split()[-1] for l in open(sys.argv[2]) if l.startswith("clip ")]
    print(compose(outline, clips, ROOT / "assets" / "music-128bpm.wav", ROOT / "out" / sys.argv[3]))
