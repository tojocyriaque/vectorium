"""
Physics Animator — Backend (FastAPI + Groq/Gemini)

Run standalone:
    uvicorn backend:app --reload

Or import `run_server` / `app` from another module (e.g. app.py).
"""

import os
import re
import json

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

load_dotenv()

app = FastAPI(title="Physics Animator API")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["POST", "GET"], allow_headers=["*"]
)

# ─── Prompt ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a physics animation engine. Given a description of a physical event,
output ONLY a single valid JSON object (no markdown, no prose, no code fences) describing the animation.

REQUIRED JSON SCHEMA:
{
  "title": "Short event title",
  "duration": <number, seconds, 1-10>,
  "background": "<css hex color>",
  "objects": [
    {
      "id": "unique_id",
      "label": "Object name",
      "color": "#hexcolor",
      "shape": "circle" | "rect" | "triangle" | "line",
      "width": <number px>,
      "height": <number px>,
      "keyframes": [
        {"t": 0.0, "x": <0-600>, "y": <0-400>, "rotation": 0, "opacity": 1, "scaleX": 1, "scaleY": 1}
      ]
    }
  ],
  "explanations": [
    {"t": 0.0, "text": "What's happening and why (physics principle), max 15 words"}
  ],
  "physics_summary": "2-3 sentences on the physics concepts demonstrated."
}

CANVAS RULES:
- Canvas is 600 wide x 400 tall. (0,0) is top-left. Ground/floor is at y=370.
- x,y of every object = its CENTER point.
- Objects must stay within 0-600 (x) and 0-400 (y) at all times — never off-screen.
- A "table" or "ledge" should be drawn as a rect object with its top surface at a specific y; objects resting on it should have their center y = (table_top_y - object_height/2).
- Round objects sitting on the ground have center y = 370 - radius.

PHYSICS RULES:
- Gravity: falling objects accelerate — keyframe spacing should reflect increasing y-displacement over equal time steps (e.g. y moves little at first, then a lot).
- Bounces: each bounce loses ~40-50% of height. A "bounce twice" event needs at least 2 visible peaks of decreasing height after the first impact, each as its own keyframe.
- Rolling: a rolling object should both translate (x changes) AND rotate (rotation increases continuously, roughly proportional to distance traveled / radius).
- Collisions: at the moment of impact, both objects must have a keyframe at the SAME t value. After collision, velocities (position deltas per second) should change realistically based on momentum (e.g. object that was struck moves faster afterward, striking object slows or reverses).
- Pendulums: x and y both change together tracing an arc (use 5+ keyframes per swing), amplitude decreases slightly each swing if "losing energy" is mentioned.
- Use AT LEAST 5-8 keyframes per object for anything involving a bounce, collision, or multi-phase motion. Two keyframes is NEVER enough for realistic motion.

GENERAL:
- duration must be long enough to show the full event clearly (typically 3-6s).
- Include a ground/table/wall object as needed for context, with shape "rect" and a fixed (non-animated, but still provide >=2 identical keyframes) position.
- Colors vivid and distinct between objects.
- explanations: at least 5, spread across the full timeline, each tied to a specific physics moment (start, mid-fall, impact, bounce, rest, etc).
- Return ONLY the JSON object."""

FEW_SHOT_USER = "A ball rolls off a table and falls to the ground, bouncing once before coming to rest"

FEW_SHOT_ASSISTANT = json.dumps({
    "title": "Ball Rolling Off a Table",
    "duration": 4,
    "background": "#dbeefc",
    "objects": [
        {
            "id": "table", "label": "Table", "color": "#8b5e3c", "shape": "rect",
            "width": 220, "height": 18,
            "keyframes": [
                {"t": 0.0, "x": 180, "y": 200, "rotation": 0, "opacity": 1, "scaleX": 1, "scaleY": 1},
                {"t": 4.0, "x": 180, "y": 200, "rotation": 0, "opacity": 1, "scaleX": 1, "scaleY": 1}
            ]
        },
        {
            "id": "ground", "label": "Ground", "color": "#a3c585", "shape": "rect",
            "width": 600, "height": 60,
            "keyframes": [
                {"t": 0.0, "x": 300, "y": 385, "rotation": 0, "opacity": 1, "scaleX": 1, "scaleY": 1},
                {"t": 4.0, "x": 300, "y": 385, "rotation": 0, "opacity": 1, "scaleX": 1, "scaleY": 1}
            ]
        },
        {
            "id": "ball", "label": "Ball", "color": "#e74c3c", "shape": "circle",
            "width": 32, "height": 32,
            "keyframes": [
                {"t": 0.0,  "x": 100, "y": 175, "rotation": 0,   "opacity": 1, "scaleX": 1, "scaleY": 1},
                {"t": 0.8,  "x": 270, "y": 175, "rotation": 180, "opacity": 1, "scaleX": 1, "scaleY": 1},
                {"t": 1.0,  "x": 290, "y": 178, "rotation": 230, "opacity": 1, "scaleX": 1, "scaleY": 1},
                {"t": 1.6,  "x": 330, "y": 280, "rotation": 400, "opacity": 1, "scaleX": 1, "scaleY": 1},
                {"t": 1.85, "x": 345, "y": 354, "rotation": 460, "opacity": 1, "scaleX": 1.2, "scaleY": 0.7},
                {"t": 2.1,  "x": 360, "y": 300, "rotation": 520, "opacity": 1, "scaleX": 1, "scaleY": 1},
                {"t": 2.4,  "x": 375, "y": 354, "rotation": 580, "opacity": 1, "scaleX": 1.15, "scaleY": 0.8},
                {"t": 2.6,  "x": 385, "y": 335, "rotation": 610, "opacity": 1, "scaleX": 1, "scaleY": 1},
                {"t": 2.9,  "x": 395, "y": 354, "rotation": 650, "opacity": 1, "scaleX": 1.05, "scaleY": 0.9},
                {"t": 4.0,  "x": 410, "y": 354, "rotation": 700, "opacity": 1, "scaleX": 1, "scaleY": 1}
            ]
        }
    ],
    "explanations": [
        {"t": 0.0,  "text": "Ball rolls along the table at constant speed."},
        {"t": 0.9,  "text": "Ball leaves the table edge, becoming a projectile."},
        {"t": 1.6,  "text": "Gravity accelerates the ball downward in an arc."},
        {"t": 1.85, "text": "Impact! Ball compresses slightly and loses energy."},
        {"t": 2.4,  "text": "Ball bounces again, but lower than before."},
        {"t": 4.0,  "text": "Friction and energy loss bring the ball to rest."}
    ],
    "physics_summary": "This demonstrates projectile motion: horizontal velocity stays constant while gravity accelerates the ball downward. Each bounce loses kinetic energy to heat and sound, so bounce height decreases until the ball settles."
}, indent=2)


class AnimationRequest(BaseModel):
    description: str


# ─── JSON cleanup & validation ────────────────────────────────────────────────

def clean_json(raw: str) -> dict:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    return json.loads(text)


def validate_and_fix(data: dict) -> dict:
    data.setdefault("title", "Physics Event")
    data.setdefault("background", "#e8f0f8")
    duration = float(data.get("duration", 4))
    duration = max(1.0, min(10.0, duration))
    data["duration"] = duration

    for obj in data.get("objects", []):
        obj.setdefault("label", "")
        obj.setdefault("color", "#4a90d9")
        obj.setdefault("shape", "rect")
        obj.setdefault("width", 30)
        obj.setdefault("height", 30)

        kfs = obj.get("keyframes") or [{"t": 0, "x": 300, "y": 200}]
        fixed = []
        for kf in kfs:
            fixed.append({
                "t": max(0.0, min(duration, float(kf.get("t", 0)))),
                "x": max(0, min(600, float(kf.get("x", 300)))),
                "y": max(0, min(400, float(kf.get("y", 200)))),
                "rotation": float(kf.get("rotation", 0)),
                "opacity": max(0.0, min(1.0, float(kf.get("opacity", 1)))),
                "scaleX": float(kf.get("scaleX", 1)),
                "scaleY": float(kf.get("scaleY", 1)),
            })
        fixed.sort(key=lambda k: k["t"])
        if fixed[0]["t"] > 0:
            first = dict(fixed[0]); first["t"] = 0.0
            fixed.insert(0, first)
        if fixed[-1]["t"] < duration:
            last = dict(fixed[-1]); last["t"] = duration
            fixed.append(last)
        obj["keyframes"] = fixed

    exps = data.get("explanations", [])
    fixed_exps = []
    for ex in exps:
        fixed_exps.append({
            "t": max(0.0, min(duration, float(ex.get("t", 0)))),
            "text": str(ex.get("text", ""))[:200],
        })
    fixed_exps.sort(key=lambda e: e["t"])
    if not fixed_exps:
        fixed_exps = [{"t": 0.0, "text": "Animation begins."}]
    data["explanations"] = fixed_exps

    data.setdefault("physics_summary", "")
    return data


# ─── Providers ─────────────────────────────────────────────────────────────────

def call_groq(description: str) -> dict:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set")
    with httpx.Client(timeout=60) as client:
        res = client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "temperature": 0.15,
                "max_tokens": 4096,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": FEW_SHOT_USER},
                    {"role": "assistant", "content": FEW_SHOT_ASSISTANT},
                    {"role": "user", "content": description},
                ],
            },
        )
    res.raise_for_status()
    return clean_json(res.json()["choices"][0]["message"]["content"])


def call_gemini(description: str) -> dict:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")
    with httpx.Client(timeout=60) as client:
        res = client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
            headers={"Content-Type": "application/json"},
            json={
                "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "contents": [
                    {"role": "user", "parts": [{"text": FEW_SHOT_USER}]},
                    {"role": "model", "parts": [{"text": FEW_SHOT_ASSISTANT}]},
                    {"role": "user", "parts": [{"text": description}]},
                ],
                "generationConfig": {
                    "temperature": 0.15, "maxOutputTokens": 4096,
                    "responseMimeType": "application/json",
                },
            },
        )
    res.raise_for_status()
    return clean_json(res.json()["candidates"][0]["content"]["parts"][0]["text"])


PROVIDERS = [("Groq", call_groq), ("Gemini", call_gemini)]


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    configured = [n for n, _ in PROVIDERS if os.getenv(f"{n.upper()}_API_KEY")]
    return {"status": "Physics Animator API is running", "configured_providers": configured}


@app.get("/providers")
def check_providers():
    result = {}
    for name, _ in PROVIDERS:
        key = os.getenv(f"{name.upper()}_API_KEY")
        result[name] = f"loaded ({key[:8]}...)" if key else "not set in .env"
    return result


@app.post("/generate")
def generate_animation(req: AnimationRequest):
    errors = []
    for name, call_fn in PROVIDERS:
        try:
            data = call_fn(req.description)
            data = validate_and_fix(data)
            data["_provider"] = name
            return data
        except ValueError as e:
            errors.append(f"{name}: {e}")
        except httpx.HTTPStatusError as e:
            errors.append(f"{name} HTTP {e.response.status_code}: {e.response.text[:200]}")
        except json.JSONDecodeError as e:
            errors.append(f"{name} bad JSON: {e}")
        except Exception as e:
            errors.append(f"{name}: {e}")
    raise HTTPException(status_code=502, detail="All providers failed. Errors:\n" + "\n".join(errors))


def run_server(host="127.0.0.1", port=8000):
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    run_server()