**Launch Reel Agent: pitch in, launch reel out** 🎬

Describe your product in a few sentences and get a 20-second launch reel, cut on the beat. Two examples are attached: **MultiTrust** (a data-privacy tool) and **Tidewater** (a flood sensor). Same pipeline, two completely different looks, both made without editing anything by hand.

**How it works:** a small team of agents.
1. **Story agent** (Claude) writes a problem → solution → proof story and picks a brand style. You edit it and approve it in the web UI.
2. **Pruna `p-image`** makes one keyframe per scene, in about 1 s each.
3. **Critic agent** (Claude vision) scores each keyframe against the reel's style anchor, rewrites weak prompts, and Pruna regenerates them.
4. **Pruna `p-video-2`** animates each keyframe into an exact 2 s clip. The critic compares the clip frames with the keyframe and rejects any that morph. A clip that still fails falls back to a clean camera move, so a reel never ships a broken shot.
5. **Compose:** cuts on a 128 BPM grid and adds typography and music, at 1080p.

**Why Pruna:** it's fast and cheap enough that the critic can afford to regenerate. A full reel with retries costs about **$1** and takes about **5 minutes**.
**Shared-key etiquette:** every generation is cached, requests are throttled well below the shared limits, the key stays server-side, and the server renders one reel at a time.

**Results:**
- MultiTrust: adding motion guards and the critic took the clips that passed from 3/10 to 8/10. The other 2 were caught and replaced, so the reel has 0 broken shots.
- Tidewater: all 10 clips passed on the first try.

💻 Repo: https://github.com/yahyoHakimov/launch-reel-agent

Since AI Hackathon 2026 · built by @Yahyo
