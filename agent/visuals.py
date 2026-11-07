"""Visuals agent: outline -> one Pruna keyframe per scene, then (optionally) a 2 s clip per scene.

Keyframes first (p-image, ~1 s, cheap) so the look can be approved before any video is spent.
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from agent import pruna

KEYFRAME_MODEL = "p-image"
CLIP_MODEL = "p-video-2"

# Keeps image-to-video faithful to the approved keyframe: motion, not reinvention.
MOTION_GUARD = ("Subtle, slow cinematic camera move only. Keep the exact scene, objects, colours and "
                "composition of the input image; nothing new appears, nothing morphs or transforms, "
                "no hands enter the frame. ")


def keyframe(scene, brand, aspect="16:9", seed=11):
    prompt = scene["visual_prompt"]
    if brand["visual_style"][:40] not in prompt:
        prompt = f"{prompt}, {brand['visual_style']}"
    return pruna.generate(KEYFRAME_MODEL, {"prompt": prompt, "aspect_ratio": aspect, "seed": seed})


CAMERA_MOVES = [
    "Slow push-in toward the centre of the frame.",
    "Slow lateral dolly from left to right, parallax on the foreground.",
    "Slow push-in with a very slight downward tilt.",
    "Gentle orbit a few degrees around the main object.",
    "Slow pull-back revealing a little more of the table.",
]


def clip(scene, keyframe_path, draft=False, seed=11, move=0):
    # Camera-only motion: asking image-to-video for story actions ("tiles turn into people")
    # makes it morph the approved keyframe, which the critic rejects.
    image_url = pruna.upload(keyframe_path)
    prompt = MOTION_GUARD + CAMERA_MOVES[move % len(CAMERA_MOVES)]
    inp = {"prompt": prompt, "image": image_url, "duration": 2,
           "resolution": "720p", "fps": 24, "draft": draft, "save_audio": False,
           "prompt_upsampling": False, "seed": seed}
    # Cache key must not depend on the expiring upload URL.
    key_inp = {**inp, "image": Path(keyframe_path).name}
    return pruna.generate_keyed(CLIP_MODEL, inp, key_inp)


def kenburns(keyframe_path, seconds=2.0, fps=30):
    """Fallback clip: a slow, deterministic push-in on the keyframe itself. Never morphs."""
    out = pruna.CACHE / f"kenburns-{Path(keyframe_path).stem}.mp4"
    if not out.exists():
        n = int(seconds * fps) + fps  # a little extra so compose can trim on the beat
        vf = (f"scale=3840:-2,zoompan=z='1+0.06*on/{n}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
              f":d={n}:s=1920x1080:fps={fps}")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(keyframe_path),
                        "-vf", vf, "-frames:v", str(n), "-pix_fmt", "yuv420p", str(out)], check=True)
    return out


def keyframes(outline, aspect="16:9"):
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(lambda s: keyframe(s, outline["brand"], aspect), outline["scenes"]))


def clips(outline, frames, draft=False):
    with ThreadPoolExecutor(max_workers=3) as pool:
        return list(pool.map(lambda i: clip(outline["scenes"][i], frames[i], draft, move=i),
                             range(len(frames))))


if __name__ == "__main__":
    outline = json.load(open(sys.argv[1]))
    frames = keyframes(outline)
    for i, f in enumerate(frames, 1):
        print(i, f)
    if "--clips" in sys.argv:
        for i, c in enumerate(clips(outline, frames, draft="--draft" in sys.argv), 1):
            print("clip", i, c)
