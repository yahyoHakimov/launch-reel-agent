# Launch Reel Agent

**Pitch in, launch reel out.** Describe a product in a few sentences. A team of agents writes a problem → solution → proof story, uses **Pruna** to paint and animate every scene, has a **Claude critic** send weak shots back, and cuts it all on the beat into a 20-second 1080p reel.

Built at the Since AI Hackathon 2026 (Turku) for the Pruna AI prize.

## The pipeline

```
 pitch ──► [1 Story agent]  Claude Opus 5.5, structured output
              brand kit (palette, tone, visual style) + 10 scenes:
              title · emphasis · picture · keyframe prompt · camera move
                │
                ▼   human approves / edits the story in the UI
           [2 Visuals agent]  Pruna p-image (~1 s per frame, 4 in parallel)
                │
                ▼
           [3 Critic agent]  Claude vision vs. a style anchor
              score < 7 → rewrites the prompt → Pruna regenerates
                │
                ▼
           [4 Visuals agent]  Pruna p-video-2, image-to-video, 2 s per scene
              camera-only motion guard (no morphing)
           [4b Critic agent]  compares clip frames with the keyframe
              score < 7 → new seed + new camera move → retry
              still failing → fallback: Ken Burns on the approved keyframe
                │
                ▼
           [5 Compose]  ffmpeg: cuts on a 128 BPM grid (4 beats/scene),
              DM Sans + DM Serif typography, music, 1920×1080 H.264
```

Agentic patterns used: prompt chaining (story → visuals → compose), parallelization (keyframes, clips and critic calls fan out), evaluator–optimizer (two critic loops), human in the loop (approve the story before any video is spent), and graceful degradation (a fallback so a reel never ships with a broken clip).

## Why Pruna

| Model | Used for | Why |
|---|---|---|
| `p-image` | one keyframe per scene | under 1 s and $0.005, so the critic can afford to regenerate |
| `p-video-2` | 2 s image-to-video clip per scene | exact 2 s durations (fits a beat grid), 720p, image-conditioned |

A full reel costs about **$1 of Pruna** and takes about **5 minutes**, including the critic retries.

**Shared-key etiquette** (all teams share one key): every generation is cached by `hash(model + input)`, requests are throttled well below the shared limits (60 images/min, 10 videos/min), the server renders one reel at a time, the key stays server-side, and look development happens on images before any video is spent.

## Results

| Run | What changed | Clips passing critic |
|---|---|---|
| v1 | draft p-video, story-driven motion prompts | not checked; visibly morphing |
| v2 | p-video-2, critic loops | 3 / 10 |
| v3 | camera-only motion + Ken Burns fallback | 8 / 10 (2 fell back), 0 broken in the reel |

## Run it

```bash
cp .env.example .env          # add PRUNA_API_KEY and ANTHROPIC_API_KEY
uv pip install anthropic pydantic requests fastapi uvicorn fonttools brotli
python -m uvicorn server:app --port 8000      # web UI
python -m agent.run examples/multitrust.txt multitrust   # or the CLI
```

Needs `ffmpeg` on PATH.

## Layout

```
agent/pruna.py     Pruna client: cache-first, throttled, sync for images, polling for video
agent/story.py     Story agent (Claude, Pydantic structured output)
agent/visuals.py   Keyframes, clips, Ken Burns fallback
agent/critic.py    Keyframe and clip critics (Claude vision), retry logic
agent/compose.py   Beat-synced cut, typography, music
agent/run.py       CLI pipeline
server.py          FastAPI + server-sent events for live progress
static/index.html  Demo UI
```

## Roadmap to SaaS

Each agent is already an isolated module with typed inputs and outputs, so the next step is to expose them as MCP tools (`write_outline`, `make_keyframes`, `critique`, `render`) behind a durable job queue. Then the same pipeline runs from the web app, from Claude Desktop, or from any agent.
