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

SYSTEM_PROMPT = """You are a physics animation engine and educational narration system. Given a description of a physical event,
output ONLY a single valid JSON object (no markdown, no prose, no code fences) describing the animation and narration.

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
      ],
      "vectors": [
        {
          "type": "velocity" | "force" | "acceleration",
          "t": 0.0,
          "x": <0-600>,
          "y": <0-400>,
          "dx": <number>,
          "dy": <number>,
          "magnitude": <0-50>
        }
      ]
    }
  ],
  "explanations": [
    {
      "t": 0.0, 
      "text": "What's happening and why (physics principle), max 15 words",
      "formula": "optional LaTeX formula string",
      "emphasis": ["velocity", "gravity", "momentum"],
      "audio_hint": "optional spoken phrase (same meaning as text)"
    }
  ],
  "physics_summary": "2-3 sentences on the physics concepts demonstrated."
}

CANVAS RULES:
- Canvas is 600 wide x 400 tall. (0,0) is top-left. Ground/floor is at y=370.
- x,y of every object = its CENTER point.
- Objects must stay within 0-600 (x) and 0-400 (y) at all times.

PHYSICS & MOTION RULES:
- Gravity: falling objects accelerate (y-displacement increases).
- Bounces: each bounce loses ~40-50% of height.
- Collisions: at the moment of impact, both objects must have a keyframe at the SAME t value. Momentum must be conserved.
- Pendulums: use 5+ keyframes per swing to trace an arc.
- Use AT LEAST 5-8 keyframes per object for complex motion. Two keyframes is NEVER enough for realistic motion.

NARRATION ENGINE & TIMING RULES (CRITICAL):
- Act like a physics professor explaining the scene live. Treat time `t` as STRUCTURED TEACHING MOMENTS.
- Only ONE main idea per timestamp.
- Examples of timing: t=0.0 (initial condition), t=0.5 (motion begins), t=1.0 (acceleration explained), t=1.5 (impact event).
- The `explanations` array represents Narration Events. Keep `text` short and time-accurate. Avoid redundant explanations.
- Include formulas ONLY when the concept is first introduced, synchronized exactly with the moment it becomes relevant (e.g., F=ma exactly at the collision t).

VECTOR RULES (SYNCHRONIZED):
- Vectors MUST be synchronized with Narration Events! A vector cannot exist without a corresponding physical narration event.
- `velocity` vectors appear when narration mentions motion (blue).
- `acceleration` vectors appear when physics mentions forces (e.g. gravity) (green).
- `force` vectors appear ONLY during interactions (collision, push, impact) (red).

GENERAL:
- duration must be long enough to show the full event clearly (typically 3-6s).
- Include a ground/table/wall object as needed for context (shape "rect").
- Colors vivid and distinct between objects.
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
            ],
            "vectors": [
                {"type": "velocity", "t": 0.0, "x": 100, "y": 175, "dx": 1, "dy": 0, "magnitude": 20},
                {"type": "acceleration", "t": 0.9, "x": 280, "y": 175, "dx": 0, "dy": 1, "magnitude": 15},
                {"type": "velocity", "t": 1.6, "x": 330, "y": 280, "dx": 1, "dy": 2, "magnitude": 30},
                {"type": "force", "t": 1.85, "x": 345, "y": 354, "dx": 0, "dy": -1, "magnitude": 40}
            ]
        }
    ],
    "explanations": [
        {"t": 0.0,  "text": "Ball rolls along the table at constant speed.", "formula": "v = \\text{const}", "emphasis": ["velocity", "constant speed"], "audio_hint": "The ball begins by rolling along the table at a constant speed."},
        {"t": 0.9,  "text": "Ball leaves the table edge, becoming a projectile.", "emphasis": ["projectile motion", "gravity"], "audio_hint": "As it leaves the edge, it becomes a projectile subject to gravity."},
        {"t": 1.6,  "text": "Gravity accelerates the ball downward in an arc.", "formula": "y = y_0 - \\frac{1}{2}gt^2", "emphasis": ["acceleration", "downward force"], "audio_hint": "Gravity accelerates the ball downward, forming a parabolic arc."},
        {"t": 1.85, "text": "Impact! Ball compresses slightly and loses energy.", "formula": "F = ma", "emphasis": ["collision", "force"], "audio_hint": "Upon impact, a sudden normal force acts on the ball."},
        {"t": 2.4,  "text": "Ball bounces again, but lower than before.", "formula": "E_{k2} < E_{k1}", "emphasis": ["energy loss", "inelastic"], "audio_hint": "Energy is lost as heat and sound, so each subsequent bounce is lower."},
        {"t": 4.0,  "text": "Friction and energy loss bring the ball to rest.", "formula": "v = 0", "emphasis": ["friction", "rest"], "audio_hint": "Eventually, friction and energy loss bring the ball completely to rest."}
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

        vectors = obj.get("vectors")
        if vectors is not None:
            fixed_vecs = []
            for v in vectors:
                fixed_vecs.append({
                    "type": str(v.get("type", "velocity")),
                    "t": max(0.0, min(duration, float(v.get("t", 0)))),
                    "x": max(0, min(600, float(v.get("x", 300)))),
                    "y": max(0, min(400, float(v.get("y", 200)))),
                    "dx": float(v.get("dx", 0)),
                    "dy": float(v.get("dy", 0)),
                    "magnitude": max(0.0, min(50.0, float(v.get("magnitude", 10)))),
                })
            obj["vectors"] = fixed_vecs

    exps = data.get("explanations", [])
    fixed_exps = []
    for ex in exps:
        fixed_exp = {
            "t": max(0.0, min(duration, float(ex.get("t", 0)))),
            "text": str(ex.get("text", ""))[:200],
        }
        if "formula" in ex:
            fixed_exp["formula"] = str(ex["formula"])
            
        fixed_exp["emphasis"] = [str(x) for x in ex.get("emphasis", []) if isinstance(x, str)]
        
        if "audio_hint" in ex:
            fixed_exp["audio_hint"] = str(ex["audio_hint"])
            
        fixed_exps.append(fixed_exp)
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