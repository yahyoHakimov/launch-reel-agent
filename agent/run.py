"""Pipeline: pitch -> outline -> keyframes -> critic -> clips -> critic -> composed reel.

    python -m agent.run examples/multitrust.txt multitrust          # full run
    python -m agent.run out/outline-multitrust.json multitrust      # reuse an approved outline
"""
import json
import sys
import time
from pathlib import Path

from agent import compose, critic, story, visuals

ROOT = Path(__file__).resolve().parent.parent


def run(source, name, log=print):
    t0 = time.time()
    out = ROOT / "out"
    if source.endswith(".json"):
        outline = json.load(open(source))
        log("1/5 outline: reused " + source)
    else:
        log("1/5 outline: writing story with Claude...")
        outline = story.write_outline(open(source).read()).model_dump()
    log("2/5 keyframes: Pruna p-image...")
    frames = visuals.keyframes(outline)
    log("3/5 critic: reviewing keyframes...")
    frames, _ = critic.refine_keyframes(outline, frames, log=log)
    (out / f"outline-{name}.json").write_text(json.dumps(outline, indent=2, ensure_ascii=False))
    log("4/5 clips: Pruna p-video-2 + critic...")
    clips = visuals.clips(outline, frames)
    clips, _ = critic.refine_clips(outline, frames, clips, log=log)
    log("5/5 compose: beat-synced cut + typography + music...")
    reel = compose.compose(outline, clips, ROOT / "assets" / "music-128bpm.wav", out / f"reel-{name}.mp4")
    log(f"done in {time.time() - t0:.0f}s -> {reel}")
    return reel


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2])
