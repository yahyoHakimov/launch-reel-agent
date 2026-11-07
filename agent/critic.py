"""Critic agent (evaluator-optimizer): Claude looks at Pruna outputs and sends weak ones back.

- Keyframes: does the image read as the scene's idea, match the reel's style, leave room for the headline?
- Clips: did image-to-video stay faithful to the approved keyframe (no morphing, no new objects)?
A failed item gets a revised prompt (keyframes) or a new seed (clips) and is regenerated, max `rounds` times.
"""
import base64
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import anthropic
from pydantic import BaseModel, Field

from agent import visuals

MODEL = "claude-opus-5-5"
PASS = 7
_client = None


def client():
    global _client
    _client = _client or anthropic.Anthropic()
    return _client


class Verdict(BaseModel):
    score: int = Field(description="1-10")
    issues: str = Field(description="One sentence; empty if none")
    revised_prompt: Optional[str] = Field(None, description="Keyframes only: a better image prompt when score < 7")


def _img(path):
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.b64encode(Path(path).read_bytes()).decode()}}


def _ask(content, effort="medium"):
    r = client().messages.parse(model=MODEL, max_tokens=4000, output_config={"effort": effort},
                                messages=[{"role": "user", "content": content}], output_format=Verdict)
    return r.parsed_output


def judge_keyframe(scene, brand, path, style_ref):
    text = (f"You are the art director of a 20 s launch reel for {brand['product_name']}.\n"
            f"Scene headline (added later on top): \"{scene['title']}\"\n"
            f"Intended picture: {scene['on_screen']}\n"
            f"Reel style: {brand['visual_style']}\n\n"
            "Image 1 is the style reference (scene 1). Image 2 is the candidate keyframe.\n"
            "Score 1-10 on: the idea reads instantly without the headline; same lighting/background/"
            "materials as the reference (not darker or busier); calm empty upper third for the headline; "
            "no text, letters or stray hands. If score < 7, write revised_prompt: a full p-image prompt that "
            "fixes the issues and keeps the reel style.")
    return _ask([_img(style_ref), _img(path), {"type": "text", "text": text}])


def _frames(video, times=(0.9, 1.8)):
    out = []
    tmp = Path(tempfile.mkdtemp())
    for t in times:
        f = tmp / f"{t}.jpg"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", str(video),
                        "-frames:v", "1", "-vf", "scale=768:-2", str(f)], check=True)
        out.append(f)
    return out


def judge_clip(scene, keyframe, video):
    mid, end = _frames(video)
    text = ("Image 1 is the approved keyframe. Images 2 and 3 are frames at 0.9 s and 1.8 s of the "
            "2-second clip animated from it.\n"
            f"Scene: {scene['on_screen']}\n"
            "Score 1-10 for faithfulness: same objects, composition and colours as the keyframe; motion is a "
            "gentle camera move; nothing morphs, appears or disappears; no hands enter. 7+ means usable.")
    return _ask([_img(keyframe), _img(mid), _img(end), {"type": "text", "text": text}], effort="low")


def refine_keyframes(outline, frames, rounds=1, log=print):
    brand, scenes = outline["brand"], outline["scenes"]
    frames = list(frames)
    for rnd in range(rounds + 1):
        with ThreadPoolExecutor(max_workers=5) as pool:
            # scene 1 is the style anchor for the rest; it is itself judged against scene 2
            verdicts = list(pool.map(
                lambda i: judge_keyframe(scenes[i], brand, frames[i], frames[1 if i == 0 else 0]),
                range(len(scenes))))
        # scene 1 stays fixed: regenerating the style anchor makes the reference drift between rounds
        weak = [i for i, v in enumerate(verdicts) if i > 0 and v.score < PASS and v.revised_prompt]
        for i, v in enumerate(verdicts):
            log(f"  keyframe {i+1}: {v.score}/10 {v.issues}")
        if not weak or rnd == rounds:
            return frames, verdicts
        for i in weak:
            scenes[i]["visual_prompt"] = verdicts[i].revised_prompt
            frames[i] = visuals.keyframe(scenes[i], brand)
            log(f"  -> regenerated keyframe {i+1}")


def refine_clips(outline, frames, clips, rounds=1, log=print):
    scenes = outline["scenes"]
    clips = list(clips)
    seeds = [11] * len(scenes)
    for rnd in range(rounds + 1):
        with ThreadPoolExecutor(max_workers=5) as pool:
            verdicts = list(pool.map(lambda i: judge_clip(scenes[i], frames[i], clips[i]), range(len(scenes))))
        weak = [i for i, v in enumerate(verdicts) if v.score < PASS]
        for i, v in enumerate(verdicts):
            log(f"  clip {i+1}: {v.score}/10 {v.issues}")
        if not weak:
            return clips, verdicts
        if rnd == rounds:
            # Never ship a morphing clip: fall back to a clean camera move on the approved keyframe.
            for i in weak:
                clips[i] = visuals.kenburns(frames[i])
                log(f"  -> clip {i+1}: fallback to Ken Burns on keyframe")
            return clips, verdicts
        for i in weak:
            seeds[i] += 100
            clips[i] = visuals.clip(scenes[i], frames[i], seed=seeds[i], move=i + 2)
            log(f"  -> regenerated clip {i+1} (seed {seeds[i]}, new camera move)")
