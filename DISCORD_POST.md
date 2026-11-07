**Launch Reel Agent — pitch in, launch reel out** 🎬

Describe a product in a few sentences and get a 20-second, beat-synced launch reel.

**How it works:** a small agent team.
1. **Story agent** (Claude): writes a problem → solution → proof story and a brand kit. You edit and approve it in the UI.
2. **Pruna `p-image`**: makes one keyframe per scene, in about 1 s each.
3. **Critic agent** (Claude vision): scores every keyframe against the style anchor, rewrites weak prompts, and Pruna regenerates them.
4. **Pruna `p-video-2`**: animates each keyframe into an exact 2 s clip. The critic compares the clip frames with the keyframe and rejects any that morph. A clip that still fails falls back to a clean camera move, so no broken shot ever ships.
5. **Compose**: cuts on a 128 BPM grid and adds typography and music, at 1080p.

**Why Pruna:** it's fast and cheap enough that the critic can afford to regenerate. A full reel with retries costs about $1 and takes about 5 minutes. Every generation is cached and throttled, and the key stays server-side, so we play nice with the shared key.

**Results:** with motion guards and the critic, 8 of 10 clips passed on the first pass, up from 3 of 10, and the reel had 0 broken shots.

🎥 Demo: <VIDEO LINK>
💻 Repo: <REPO LINK>

Team <TEAM NAME> · Since AI Hackathon 2026
