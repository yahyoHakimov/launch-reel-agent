"""Demo server: pitch -> editable outline -> approve -> live pipeline progress -> reel.

    ../.venv/bin/python -m uvicorn server:app --port 8000

Keys stay server-side (.env); the browser only sees generated files.
"""
import json
import queue
import re
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent import compose, critic, story, visuals

ROOT = Path(__file__).resolve().parent
app = FastAPI(title="Launch Reel Agent")
app.mount("/cache", StaticFiles(directory=ROOT / "cache"), name="cache")
app.mount("/out", StaticFiles(directory=ROOT / "out"), name="out")

JOBS = {}
_render_lock = threading.Lock()  # one render at a time: the Pruna key is shared by every team


class Pitch(BaseModel):
    pitch: str


class RenderReq(BaseModel):
    outline: dict


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/examples")
def examples():
    return {p.stem: p.read_text() for p in sorted((ROOT / "examples").glob("*.txt"))}


@app.post("/api/outline")
def outline(req: Pitch):
    if len(req.pitch.strip()) < 40:
        raise HTTPException(400, "Describe the product in a few sentences.")
    return story.write_outline(req.pitch[:6000]).model_dump()


def _url(p):
    p = Path(p)
    return f"/{p.parent.name}/{p.name}"


def _render(job_id, outline):
    q = JOBS[job_id]["events"]
    emit = lambda kind, **kw: q.put({"kind": kind, "t": round(time.time() - t0, 1), **kw})
    t0 = time.time()
    try:
        with _render_lock:
            emit("step", n=2, text="Pruna p-image: one keyframe per scene")
            frames = visuals.keyframes(outline)
            emit("frames", urls=[_url(f) for f in frames])

            emit("step", n=3, text="Claude critic: reviewing keyframes")
            frames, verdicts = critic.refine_keyframes(outline, frames, log=lambda m: emit("log", text=m))
            emit("frames", urls=[_url(f) for f in frames], scores=[v.score for v in verdicts])

            emit("step", n=4, text="Pruna p-video-2: animating + critic")
            clips = visuals.clips(outline, frames)
            clips, verdicts = critic.refine_clips(outline, frames, clips, log=lambda m: emit("log", text=m))
            emit("clips", scores=[v.score for v in verdicts])
            # keep everything needed to re-cut this reel without regenerating anything
            (ROOT / "out" / f"job-{job_id[:6]}.json").write_text(json.dumps(
                {"outline": outline, "frames": [str(f) for f in frames], "clips": [str(c) for c in clips]},
                indent=2, ensure_ascii=False))

            emit("step", n=5, text="Compose: beat-synced cut, typography, music")
            name = re.sub(r"[^a-z0-9]+", "-", outline["brand"]["product_name"].lower()).strip("-") or "reel"
            reel = compose.compose(outline, clips, ROOT / "assets" / "music-128bpm.wav",
                                   ROOT / "out" / f"reel-{name}-{job_id[:6]}.mp4")
            emit("done", url=_url(reel))
    except Exception as e:  # surface to the UI instead of hanging the stream
        emit("error", text=str(e)[:400])
    finally:
        q.put(None)


@app.post("/api/render")
def render(req: RenderReq):
    if _render_lock.locked():
        raise HTTPException(429, "A reel is already rendering; try again in a few minutes.")
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {"events": queue.Queue()}
    threading.Thread(target=_render, args=(job_id, req.outline), daemon=True).start()
    return {"job": job_id}


@app.get("/api/jobs/{job_id}/events")
def events(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404)

    def stream():
        while True:
            ev = job["events"].get()
            if ev is None:
                return
            yield f"data: {json.dumps(ev)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
