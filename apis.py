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

SYSTEM_PROMPT = """You are a deterministic physics simulation engine, scientific animator, and educational narration system designer. Given a description of a physical event,
output ONLY a single valid JSON object (no markdown, no prose, no code fences) describing the animation and narration. This is a scientific physics simulation.

REQUIRED JSON SCHEMA:
{
  "title": "Short event title",
  "duration": <number, seconds, 1-10>,
  "background": "<css hex color>",
  "objects": [
    {
      "id": "unique_id",
      "label": "Object name",
      "visual": {
        "type": "billiard_ball" | "sphere" | "cube" | "box" | "table" | "ground" | "obstacle",
        "color": "#hexcolor",
        "material": "glossy" | "matte" | "wood" | "metal" | "glass"
      },
      "width": <number px>,
      "height": <number px>,
      "keyframes": [
        {"t": 0.0, "x": <0-600>, "y": <0-400>, "rotation": 0, "opacity": 1, "scaleX": 1, "scaleY": 1}
      ],
      "vectors": [
        {
          "type": "velocity" | "force" | "acceleration",
          "t": 0.0,
          "dx": <number>,
          "dy": <number>,
          "magnitude": <0-50>
        }
      ]
    }
  ],
  "narration": [
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

KEYFRAME DENSITY RULE (CRITICAL):
- The frontend interpolates LINEARLY between keyframes. You MUST place keyframes along the actual physics curve.
- For parabolic free-fall: use 6+ keyframes tracing the parabola (y-spacing increases quadratically).
- For bounces: place a keyframe at EVERY apex and EVERY ground contact. Each bounce must be lower.
- For rolling: place keyframes at regular intervals showing horizontal progression.
- Two keyframes is NEVER enough for curved motion. Use AT LEAST 6-10 keyframes per moving object.

PHYSICS & MOTION RULES (STRICT & DETERMINISTIC):
- ABSOLUTE RULE: Objects MUST NEVER overlap or interpenetrate.
- COLLISION RULE: Collisions MUST occur EXACTLY at a shared keyframe timestamp `t`. 
  Velocity change MUST be a perfect step function at that exact timestamp.
  The keyframe at collision time shows contact position.
  The very next keyframe MUST reflect the new velocity instantly.
- STRAIGHT-LINE SEGMENTS ONLY: Every segment between non-collision keyframes 
  must be perfectly straight (constant velocity vector). 
  Do NOT add any intermediate keyframes that create even slight curvature.
  For straight rolling (billiard balls), use exactly TWO keyframes per phase.
- NO PRE-COLLISION BENDING: Never generate keyframes that make an object 
  gradually turn before the collision timestamp. Direction changes are ONLY 
  allowed at the collision keyframe itself.

ROLLING ROTATION RULE:
- The frontend computes rotation AUTOMATICALLY for sphere/billiard_ball types from horizontal displacement.
- Do NOT manually set rotation values for rolling objects — set rotation to 0 in ALL keyframes.
- The engine calculates: rotation = horizontal_distance / radius (rolling without slipping).

VECTOR RULES (SYNCHRONIZED):
- Vector x,y values are IGNORED by the renderer — vectors are always drawn from the object's current interpolated position. Only specify t, type, dx, dy, and magnitude.
- For velocity vectors: dx,dy are also ignored — the renderer computes velocity direction from the actual position derivative. Only the `t` value matters (controls when the vector is visible).
- For acceleration vectors: dx,dy specify the direction of the acceleration (e.g., dx=0, dy=1 for gravity pointing down).
- For force vectors: dx,dy specify the direction, and they appear ONLY during interactions (collision, push, impact) with a tight 0.15s window.
- Vectors MUST be synchronized with Narration Events.

NARRATION ENGINE & TIMING RULES (CRITICAL):
- Act like a physics professor explaining the scene live. Treat time `t` as STRUCTURED TEACHING MOMENTS.
- Only ONE main idea per timestamp.
- Include formulas ONLY when the concept is first introduced, synchronized exactly with the moment it becomes relevant.

GENERAL:
- duration must be long enough to show the full event clearly (typically 3-6s).
- Include a ground/table/wall object as needed for context (type "table" or "ground").
- Colors vivid and distinct between objects.
- Return ONLY the JSON object."""

FEW_SHOT_USER = "A ball rolls off a table and falls to the ground, bouncing once before coming to rest"

FEW_SHOT_ASSISTANT = json.dumps({
    "title": "Ball Rolling Off a Table",
    "duration": 4,
    "background": "#dbeefc",
    "objects": [
        {
            "id": "table", "label": "Table",
            "visual": {"type": "table", "color": "#8b5e3c", "material": "wood"},
            "width": 220, "height": 18,
            "keyframes": [
                {"t": 0.0, "x": 180, "y": 200, "rotation": 0, "opacity": 1, "scaleX": 1, "scaleY": 1},
                {"t": 4.0, "x": 180, "y": 200, "rotation": 0, "opacity": 1, "scaleX": 1, "scaleY": 1}
            ]
        },
        {
            "id": "ground", "label": "Ground",
            "visual": {"type": "ground", "color": "#a3c585", "material": "matte"},
            "width": 600, "height": 60,
            "keyframes": [
                {"t": 0.0, "x": 300, "y": 385, "rotation": 0, "opacity": 1, "scaleX": 1, "scaleY": 1},
                {"t": 4.0, "x": 300, "y": 385, "rotation": 0, "opacity": 1, "scaleX": 1, "scaleY": 1}
            ]
        },
        {
            "id": "ball", "label": "Ball",
            "visual": {"type": "billiard_ball", "color": "#e74c3c", "material": "glossy"},
            "width": 32, "height": 32,
            "keyframes": [
                {"t": 0.0,  "x": 100, "y": 175, "rotation": 0, "opacity": 1, "scaleX": 1, "scaleY": 1},
                {"t": 0.4,  "x": 185, "y": 175, "rotation": 0, "opacity": 1, "scaleX": 1, "scaleY": 1},
                {"t": 0.8,  "x": 270, "y": 175, "rotation": 0, "opacity": 1, "scaleX": 1, "scaleY": 1},
                {"t": 1.0,  "x": 290, "y": 180, "rotation": 0, "opacity": 1, "scaleX": 1, "scaleY": 1},
                {"t": 1.2,  "x": 305, "y": 210, "rotation": 0, "opacity": 1, "scaleX": 1, "scaleY": 1},
                {"t": 1.4,  "x": 320, "y": 260, "rotation": 0, "opacity": 1, "scaleX": 1, "scaleY": 1},
                {"t": 1.6,  "x": 335, "y": 320, "rotation": 0, "opacity": 1, "scaleX": 1, "scaleY": 1},
                {"t": 1.75, "x": 345, "y": 354, "rotation": 0, "opacity": 1, "scaleX": 1.15, "scaleY": 0.8},
                {"t": 1.9,  "x": 355, "y": 320, "rotation": 0, "opacity": 1, "scaleX": 1, "scaleY": 1},
                {"t": 2.1,  "x": 365, "y": 300, "rotation": 0, "opacity": 1, "scaleX": 1, "scaleY": 1},
                {"t": 2.3,  "x": 375, "y": 330, "rotation": 0, "opacity": 1, "scaleX": 1, "scaleY": 1},
                {"t": 2.5,  "x": 382, "y": 354, "rotation": 0, "opacity": 1, "scaleX": 1.08, "scaleY": 0.9},
                {"t": 2.7,  "x": 390, "y": 340, "rotation": 0, "opacity": 1, "scaleX": 1, "scaleY": 1},
                {"t": 2.9,  "x": 398, "y": 354, "rotation": 0, "opacity": 1, "scaleX": 1.03, "scaleY": 0.95},
                {"t": 4.0,  "x": 410, "y": 354, "rotation": 0, "opacity": 1, "scaleX": 1, "scaleY": 1}
            ],
            "vectors": [
                {"type": "velocity", "t": 0.0, "dx": 1, "dy": 0, "magnitude": 20},
                {"type": "acceleration", "t": 1.0, "dx": 0, "dy": 1, "magnitude": 15},
                {"type": "velocity", "t": 1.4, "dx": 1, "dy": 2, "magnitude": 30},
                {"type": "force", "t": 1.75, "dx": 0, "dy": -1, "magnitude": 40}
            ]
        }
    ],
    "narration": [
        {"t": 0.0,  "text": "Ball rolls along the table at constant speed.", "formula": "v = \\text{const}", "emphasis": ["velocity", "constant speed"], "audio_hint": "The ball begins by rolling along the table at a constant speed."},
        {"t": 1.0,  "text": "Ball leaves the table edge, becoming a projectile.", "emphasis": ["projectile motion", "gravity"], "audio_hint": "As it leaves the edge, it becomes a projectile subject to gravity."},
        {"t": 1.4,  "text": "Gravity accelerates the ball downward in a parabolic arc.", "formula": "y = y_0 + \\frac{1}{2}gt^2", "emphasis": ["acceleration", "parabola"], "audio_hint": "Gravity accelerates the ball downward, forming a parabolic arc."},
        {"t": 1.75, "text": "Impact! Normal force acts, ball compresses and loses energy.", "formula": "F = ma", "emphasis": ["collision", "normal force"], "audio_hint": "Upon impact, a sudden normal force acts on the ball."},
        {"t": 2.5,  "text": "Second bounce is lower — kinetic energy was lost.", "formula": "E_{k2} < E_{k1}", "emphasis": ["energy loss", "inelastic"], "audio_hint": "Energy is lost as heat and sound, so each subsequent bounce is lower."},
        {"t": 4.0,  "text": "Friction and energy loss bring the ball to rest.", "formula": "v = 0", "emphasis": ["friction", "rest"], "audio_hint": "Eventually, friction and energy loss bring the ball completely to rest."}
    ],
    "physics_summary": "This demonstrates projectile motion: horizontal velocity stays constant while gravity accelerates the ball downward. Each bounce loses kinetic energy to heat and sound, so bounce height decreases until the ball settles."
}, indent=2)


class AnimationRequest(BaseModel):
    description: str


# ─── JSON cleanup & validation ────────────────────────────────────────────────

def _interp_at(sorted_kfs, t, prop, default=0):
    """
    Figuring out exactly where an object is at a specific time 't'.
    Since we only have keyframes at certain timestamps, we connect the dots
    and linearly interpolate the properties (like x, y position) in between them.
    This acts just like the frontend's get_prop function, but for our backend checks.
    """
    if not sorted_kfs:
        return default
    if t <= sorted_kfs[0]["t"]:
        return sorted_kfs[0].get(prop, default)
    if t >= sorted_kfs[-1]["t"]:
        return sorted_kfs[-1].get(prop, default)
    for a, b in zip(sorted_kfs, sorted_kfs[1:]):
        if a["t"] <= t <= b["t"]:
            span = b["t"] - a["t"]
            alpha = 0 if span == 0 else (t - a["t"]) / span
            va = a.get(prop, default)
            vb = b.get(prop, default)
            return va + (vb - va) * alpha
    return default

def clean_json(raw: str) -> dict:
    """
    LLMs can be messy and sometimes wrap their JSON output in markdown blocks
    like ```json ... ``` or add extra text. This function aggressively strips
    away all that fluff so we just get the raw, parseable dictionary.
    """
    text = raw.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    return json.loads(text)


def validate_and_fix(data: dict) -> dict:
    """
    The main physics bouncer! 
    It takes the raw JSON generated by the AI and makes sure it follows all
    our strict physics rules. It sets safe defaults, cleans up old formats,
    forces linear motion, and fixes vectors so the frontend doesn't crash.
    """
    data.setdefault("title", "Physics Event")
    data.setdefault("background", "#e8f0f8")
    duration = float(data.get("duration", 4))
    duration = max(1.0, min(10.0, duration))
    data["duration"] = duration

    for obj in data.get("objects", []):
        obj.setdefault("label", "")
        
        # Migrate old shape/color to new visual node
        if "visual" not in obj:
            old_shape = obj.get("shape", "box")
            if old_shape == "circle":
                v_type = "sphere"
            elif old_shape == "rect":
                v_type = "box"
            else:
                v_type = old_shape
                
            obj["visual"] = {
                "type": v_type,
                "color": obj.get("color", "#4a90d9"),
                "material": "matte"
            }
            
        # Ensure visual defaults
        visual = obj["visual"]
        visual.setdefault("type", "box")
        visual.setdefault("color", "#4a90d9")
        visual.setdefault("material", "matte")
        
        # remove old shape/color if present
        obj.pop("shape", None)
        obj.pop("color", None)

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

        # Make sure vectors are actually attached to the objects
        # The LLM might guess the x,y coordinates, but we recalculate them
        # exactly based on the interpolated position at time 't'.
        vectors = obj.get("vectors")
        if vectors is not None:
            fixed_vecs = []
            for v in vectors:
                v_t = max(0.0, min(duration, float(v.get("t", 0))))
                # Snap vector position to object's interpolated position at this t
                v_x = _interp_at(fixed, v_t, "x", 300)
                v_y = _interp_at(fixed, v_t, "y", 200)
                fixed_vecs.append({
                    "type": str(v.get("type", "velocity")),
                    "t": v_t,
                    "x": v_x,
                    "y": v_y,
                    "dx": float(v.get("dx", 0)),
                    "dy": float(v.get("dy", 0)),
                    "magnitude": max(0.0, min(50.0, float(v.get("magnitude", 10)))),
                })
            obj["vectors"] = fixed_vecs

        # For spheres and billiard balls, we don't trust the LLM's rotation.
        # We zero it out here and let the frontend calculate the exact rolling 
        # rotation based on the actual horizontal displacement.
        if visual.get("type") in ("billiard_ball", "sphere"):
            for kf in obj["keyframes"]:
                kf["rotation"] = 0.0

    # Map old explanations to narration
    if "explanations" in data and "narration" not in data:
        data["narration"] = data.pop("explanations")
        
    exps = data.get("narration", [])
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
    data["narration"] = fixed_exps

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

    print("All providers failed !!!! ", errors)
    raise HTTPException(status_code=502, detail="All providers failed. Errors:\n" + "\n".join(errors))


def run_server(host="127.0.0.1", port=8000):
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    run_server()