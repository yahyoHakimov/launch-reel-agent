"""Pruna API client: cache-first, rate-limited, sync for images, polling for video.

The hackathon key is shared by every team, so this client:
- caches every generation by hash(model + input) and never regenerates a hit
- throttles requests per model family (shared limits: images 250/min, video 30/min)
- retries 429/5xx with backoff, and never loops forever
"""
import hashlib
import json
import os
import threading
import time
from pathlib import Path

import requests

BASE = "https://api.pruna.ai"
ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"


def _load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                if v.strip():
                    os.environ.setdefault(k.strip(), v.strip().strip('"'))


_load_env()

# Stay well under the shared limits so we never slow down other teams.
_MIN_INTERVAL = {"image": 60 / 60, "video": 60 / 10}  # 60 img/min, 10 video/min
_last_call = {"image": 0.0, "video": 0.0}
_lock = threading.Lock()


class PrunaError(RuntimeError):
    pass


def _key():
    k = os.environ.get("PRUNA_API_KEY")
    if not k:
        raise PrunaError("PRUNA_API_KEY missing: put it in reel-agent/.env")
    return k


def _family(model):
    return "video" if "video" in model or model.startswith(("wan-", "vace")) else "image"


def _throttle(family):
    with _lock:
        wait = _last_call[family] + _MIN_INTERVAL[family] - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call[family] = time.monotonic()


def _full(url):
    return url if url.startswith("http") else BASE + url


def _request(method, url, **kw):
    r = None
    for attempt in range(5):
        try:
            r = requests.request(method, url, timeout=90, **kw)
        except (requests.ConnectionError, requests.Timeout) as e:  # DNS blips, dropped Wi-Fi
            if attempt == 4:
                raise PrunaError(f"{method} {url}: network error after retries: {e}") from e
            time.sleep(2 ** attempt)
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(2 ** attempt)
            continue
        return r
    raise PrunaError(f"{method} {url} failed after retries: {r.status_code} {r.text[:200]}")


def upload(path):
    """Upload a local file, return its URL for use as a model input (expires ~24h)."""
    r = _request("POST", f"{BASE}/v1/files", headers={"apikey": _key()},
                 files={"content": open(path, "rb")})
    r.raise_for_status()
    return r.json()["urls"]["get"]


def generate(model, inp, ext=None, timeout=600):
    """Run `model` on `inp`; return the local path of the cached output file."""
    return generate_keyed(model, inp, inp, ext, timeout)


def generate_keyed(model, inp, key_inp, ext=None, timeout=600):
    """Like generate(), but cache on `key_inp` (e.g. with expiring upload URLs replaced)."""
    family = _family(model)
    ext = ext or (".mp4" if family == "video" else ".jpg")
    digest = hashlib.sha256(json.dumps([model, key_inp], sort_keys=True).encode()).hexdigest()[:16]
    out = CACHE / f"{model}-{digest}{ext}"
    if out.exists():
        return out

    headers = {"apikey": _key(), "Model": model, "Content-Type": "application/json"}
    if family == "image":
        headers["Try-Sync"] = "true"
    _throttle(family)
    r = _request("POST", f"{BASE}/v1/predictions", headers=headers, json={"input": inp})
    if r.status_code == 422:
        raise PrunaError(f"moderation blocked: {r.text[:200]}")
    if r.status_code >= 400:
        raise PrunaError(f"{r.status_code}: {r.text[:300]}")
    body = r.json()

    url = body.get("generation_url") if body.get("status") == "succeeded" else None
    if not url:
        get_url = _full(body["get_url"])
        poll = 1 if family == "image" else 3
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(poll)
            s = _request("GET", get_url, headers={"apikey": _key()}).json()
            if s["status"] == "succeeded":
                url = s["generation_url"]
                break
            if s["status"] == "failed":
                raise PrunaError(f"generation failed: {s.get('error')} {s.get('moderation') or ''}")
        else:
            raise PrunaError(f"timed out after {timeout}s: {get_url}")

    data = _request("GET", _full(url), headers={"apikey": _key()})
    data.raise_for_status()
    CACHE.mkdir(exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".part")
    tmp.write_bytes(data.content)
    tmp.rename(out)
    (out.with_suffix(".json")).write_text(json.dumps({"model": model, "input": inp}, indent=2))
    return out


if __name__ == "__main__":
    import sys
    prompt = " ".join(sys.argv[1:]) or "A minimal teal shield icon on warm sand paper, soft studio light"
    print(generate("p-image", {"prompt": prompt, "aspect_ratio": "16:9", "seed": 7}))
