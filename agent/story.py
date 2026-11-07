"""Story agent: product pitch -> brand kit + 10-scene problem/solution/proof outline.

Every scene carries a Pruna `visual_prompt` (keyframe) and `motion_prompt` (clip),
so the outline drives the visuals agent directly.
"""
import json
import sys
from typing import List, Literal

import anthropic
from pydantic import BaseModel, Field

from agent import pruna  # noqa: F401  (loads .env)

MODEL = "claude-opus-5-5"


class BrandKit(BaseModel):
    product_name: str
    one_liner: str
    tone: str = Field(description="3-5 words, e.g. 'calm, precise, human'")
    palette: List[str] = Field(description="4-5 hex colours: background, ink, accent, accent2, highlight")
    visual_style: str = Field(description="Shared style suffix appended to every image prompt, so all scenes look like one film")


class Scene(BaseModel):
    act: Literal["problem", "solution", "proof"]
    title: str = Field(description="On-screen headline, max 7 words")
    emphasis: str = Field(description="The one word or phrase from the title set in the accent colour")
    on_screen: str = Field(description="What the viewer sees, one sentence")
    visual_prompt: str = Field(description="Pruna p-image prompt for the scene's keyframe. No text or letters in the image; leave calm negative space for the headline.")
    motion_prompt: str = Field(description="Camera-only move for 2 seconds (push-in, dolly, orbit). Objects must not change, transform or appear.")
    seconds: float


class Outline(BaseModel):
    brand: BrandKit
    scenes: List[Scene]


SYSTEM = """You write 20-second launch reels for products, in the style of a sharp motion-design studio.

Story structure (always):
- Problem (4 scenes): the stakes, then why existing approaches fail. The viewer must feel the pain before the product appears.
- Solution (4 scenes): the product name reveal, then how it works in 3 concrete steps.
- Proof (2 scenes): one real number from the input, then the closing promise with the product name.

Rules:
- 10 scenes, 2.0 s each (the final scene 2.0 s too) = 20 s total.
- Titles are short, concrete and spoken-language; no buzzwords ("revolutionary", "seamless", "unlock").
- Use only facts present in the input. Never invent metrics; if no number exists, make the proof scene about a concrete outcome.
- Visual prompts describe photoreal or tactile 3D scenes in one consistent style (from brand.visual_style), never containing any text, letters, logos or UI copy, with clear negative space for a headline.
"""


def write_outline(pitch: str) -> Outline:
    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": "high"},
        system=SYSTEM,
        messages=[{"role": "user", "content": f"Product input:\n\n{pitch}"}],
        output_format=Outline,
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"model refused: {response.stop_details}")
    return response.parsed_output


if __name__ == "__main__":
    pitch = open(sys.argv[1]).read() if len(sys.argv) > 1 else sys.stdin.read()
    outline = write_outline(pitch)
    print(json.dumps(outline.model_dump(), indent=2, ensure_ascii=False))
