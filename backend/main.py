from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import json
import os
import re
import httpx

load_dotenv()

app = FastAPI(title="Physics Animator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

SYSTEM_PROMPT = """You are a physics animation engine. When given a description of a physical event,
you output ONLY valid JSON (no markdown, no explanation) describing the animation.

The JSON must follow this exact structure:
{
  "title": "Short event title",
  "duration": <number of seconds, 1-10>,
  "background": "<css color for scene bg, e.g. #e8f4f8>",
  "objects": [
    {
      "id": "unique_id",
      "label": "Object name",
      "color": "#hexcolor",
      "shape": "circle" | "rect" | "triangle" | "line",
      "width": <number, pixels at 600px canvas>,
      "height": <number>,
      "keyframes": [
        { "t": 0.0, "x": <0-600>, "y": <0-400>, "rotation": 0, "opacity": 1, "scaleX": 1, "scaleY": 1 },
        ...more keyframes at different t values up to duration
      ]
    }
  ],
  "explanations": [
    { "t": 0.0, "text": "What is happening at this moment and why (physics principle)" },
    ...at least 4 explanations spread across the timeline
  ],
  "physics_summary": "2-3 sentences summarizing the physics concepts demonstrated."
}

Rules:
- Canvas is 600x400. Origin (0,0) is top-left. Ground is y=370.
- x,y is the CENTER of the object.
- Use realistic physics motion (gravity makes objects accelerate downward, bouncing loses energy, etc).
- Every object needs at least 3 keyframes.
- Keyframe t values must be between 0 and duration (inclusive).
- Produce at least 2 objects (include environment objects like ground, walls if needed).
- Colors should be vivid and distinct.
- Keep explanations concise (max 15 words each).
- Return ONLY the JSON object. No prose. No markdown fences."""


class AnimationRequest(BaseModel):
    description: str


def clean_json(raw: str) -> dict:
    """Strip markdown fences and parse JSON."""
    text = raw.strip()
    # Remove ```json ... ``` or ``` ... ```
    text = re.sub(r"^```(?:json)?", "", text).rstrip("`").strip()
    return json.loads(text)


# ─── Provider: Groq ──────────────────────────────────────────────────────────

def call_groq(description: str) -> dict:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set")

    with httpx.Client(timeout=60) as client:
        res = client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama3-70b-8192",
                "temperature": 0.3,
                "max_tokens": 2048,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": description},
                ],
            },
        )
    res.raise_for_status()
    raw = res.json()["choices"][0]["message"]["content"]
    return clean_json(raw)


# ─── Provider: Gemini ────────────────────────────────────────────────────────

def call_gemini(description: str) -> dict:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")

    prompt = f"{SYSTEM_PROMPT}\n\nEvent to animate:\n{description}"

    with httpx.Client(timeout=60) as client:
        res = client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.3, "maxOutputTokens": 2048},
            },
        )
    res.raise_for_status()
    raw = res.json()["candidates"][0]["content"]["parts"][0]["text"]
    return clean_json(raw)


# ─── Fallback chain ──────────────────────────────────────────────────────────

PROVIDERS = [
    ("Groq",   call_groq),
    ("Gemini", call_gemini),
]


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    configured = [name for name, _ in PROVIDERS if os.getenv(f"{name.upper()}_API_KEY")]
    return {
        "status": "Physics Animator API is running",
        "configured_providers": configured,
    }


@app.post("/generate")
def generate_animation(req: AnimationRequest):
    errors = []

    for name, call_fn in PROVIDERS:
        try:
            data = call_fn(req.description)
            data["_provider"] = name   # tell the frontend which one was used
            return data
        except ValueError as e:
            # Key not configured — skip silently
            errors.append(f"{name}: {e}")
        except httpx.HTTPStatusError as e:
            errors.append(f"{name} HTTP {e.response.status_code}: {e.response.text[:200]}")
        except json.JSONDecodeError as e:
            errors.append(f"{name} bad JSON: {e}")
        except Exception as e:
            errors.append(f"{name}: {e}")

    raise HTTPException(
        status_code=502,
        detail="All providers failed. Errors:\n" + "\n".join(errors),
    )
