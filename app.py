"""
Physics Animator — single-file app
Combines FastAPI backend (Groq/Gemini) + Pygame frontend.

Setup:
    pip install fastapi uvicorn httpx python-dotenv pygame requests

.env file (same folder):
    GROQ_API_KEY=gsk_...
    GEMINI_API_KEY=AIza...

Run:
    python app.py
"""

import os
import re
import json
import sys
import threading
import textwrap

import httpx
import requests
import pygame
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

load_dotenv()

# ════════════════════════════════════════════════════════════════════════════
# BACKEND  (FastAPI)
# ════════════════════════════════════════════════════════════════════════════

app = FastAPI(title="Physics Animator API")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["POST", "GET"], allow_headers=["*"]
)

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


def run_server():
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


# ════════════════════════════════════════════════════════════════════════════
# FRONTEND  (Pygame)
# ════════════════════════════════════════════════════════════════════════════

API_URL = "http://127.0.0.1:8000/generate"

WIDTH, HEIGHT = 600, 560
CANVAS_H = 400
FPS = 60

WHITE, BLACK, GRAY = (255, 255, 255), (20, 20, 30), (90, 90, 110)
PURPLE, BLUE, GREEN, RED = (167, 139, 250), (96, 165, 250), (110, 231, 183), (248, 113, 113)


def lerp(a, b, t):
    return a + (b - a) * t


def ease_in_out(t):
    return 2 * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 2 / 2


def get_prop(keyframes, t, prop, default=0):
    kfs = sorted(keyframes, key=lambda k: k["t"])
    if t <= kfs[0]["t"]:
        return kfs[0].get(prop, default)
    if t >= kfs[-1]["t"]:
        return kfs[-1].get(prop, default)
    for a, b in zip(kfs, kfs[1:]):
        if a["t"] <= t <= b["t"]:
            span = b["t"] - a["t"]
            alpha = 0 if span == 0 else (t - a["t"]) / span
            alpha = ease_in_out(alpha)
            return lerp(a.get(prop, default), b.get(prop, default), alpha)
    return default


def hex_to_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return (100, 150, 200)


def draw_object(surface, obj, t):
    x = get_prop(obj["keyframes"], t, "x", 300)
    y = get_prop(obj["keyframes"], t, "y", 200)
    rotation = get_prop(obj["keyframes"], t, "rotation", 0)
    opacity = get_prop(obj["keyframes"], t, "opacity", 1)
    scale_x = get_prop(obj["keyframes"], t, "scaleX", 1)
    scale_y = get_prop(obj["keyframes"], t, "scaleY", 1)

    w = obj.get("width", 30) * scale_x
    h = obj.get("height", 30) * scale_y
    color = hex_to_rgb(obj.get("color", "#4a90d9"))
    shape = obj.get("shape", "rect")
    alpha = max(0, min(255, int(opacity * 255)))

    pad = int(max(w, h) * 1.6) + 4
    obj_surf = pygame.Surface((pad, pad), pygame.SRCALPHA)
    cx, cy = pad // 2, pad // 2

    if shape == "circle":
        r = int(w / 2)
        pygame.draw.circle(obj_surf, (*color, alpha), (cx, cy), r)
        pygame.draw.circle(obj_surf, (0, 0, 0, 40), (cx, cy), r, 2)
        pygame.draw.circle(obj_surf, (255, 255, 255, 90),
                            (int(cx - r * 0.3), int(cy - r * 0.3)), max(2, int(r * 0.25)))
    elif shape == "rect":
        rect = pygame.Rect(0, 0, int(w), int(h)); rect.center = (cx, cy)
        pygame.draw.rect(obj_surf, (*color, alpha), rect, border_radius=3)
        pygame.draw.rect(obj_surf, (0, 0, 0, 40), rect, 2, border_radius=3)
    elif shape == "triangle":
        pts = [(cx, cy - h / 2), (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)]
        pygame.draw.polygon(obj_surf, (*color, alpha), pts)
        pygame.draw.polygon(obj_surf, (0, 0, 0, 40), pts, 2)
    elif shape == "line":
        thickness = max(2, int(h))
        pygame.draw.line(obj_surf, (*color, alpha), (cx - w / 2, cy), (cx + w / 2, cy), thickness)

    rotated = pygame.transform.rotate(obj_surf, -rotation)
    rect = rotated.get_rect(center=(int(x), int(y)))
    surface.blit(rotated, rect)

    label = obj.get("label", "")
    if label and shape != "line":
        font = pygame.font.SysFont("couriernew", 12, bold=True)
        text = font.render(label, True, (60, 60, 70))
        surface.blit(text, text.get_rect(center=(int(x), int(y + h / 2 + 12))))


def draw_button(surface, rect, text, font, bg, fg=WHITE):
    pygame.draw.rect(surface, bg, rect, border_radius=8)
    label = font.render(text, True, fg)
    surface.blit(label, label.get_rect(center=rect.center))


def wrap_text(text, font, max_width):
    words = text.split(" ")
    lines, current = [], ""
    for w in words:
        test = (current + " " + w).strip()
        if font.size(test)[0] <= max_width:
            current = test
        else:
            lines.append(current); current = w
    if current:
        lines.append(current)
    return lines


def get_current_explanation(explanations, t):
    sorted_exps = sorted(explanations, key=lambda e: e["t"])
    best = sorted_exps[0]
    for e in sorted_exps:
        if e["t"] <= t:
            best = e
    return best


def fetch_animation(description):
    res = requests.post(API_URL, json={"description": description}, timeout=120)
    res.raise_for_status()
    return res.json()


def run_frontend():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Physics Animator")
    clock = pygame.time.Clock()

    font_title = pygame.font.SysFont("couriernew", 22, bold=True)
    font_small = pygame.font.SysFont("couriernew", 13)
    font_tiny = pygame.font.SysFont("couriernew", 11)
    font_input = pygame.font.SysFont("arial", 16)

    input_text = "A ball rolls off a table and bounces twice"
    input_active = True
    anim_data = None
    current_t = 0.0
    playing = False
    loading = False
    error_msg = ""

    scrubber_rect = pygame.Rect(20, CANVAS_H + 90 + 110, WIDTH - 40, 6)
    play_btn = pygame.Rect(20, CANVAS_H + 110 + 110, 90, 32)
    reset_btn = pygame.Rect(120, CANVAS_H + 110 + 110, 90, 32)
    generate_btn = pygame.Rect(WIDTH - 120, 20, 100, 32)
    input_box = pygame.Rect(20, 20, WIDTH - 150, 32)
    canvas_top = 110

    # Fix: layout constants computed properly below (override placeholders)
    scrubber_rect = pygame.Rect(20, canvas_top + CANVAS_H + 90, WIDTH - 40, 6)
    play_btn = pygame.Rect(20, canvas_top + CANVAS_H + 110, 90, 32)
    reset_btn = pygame.Rect(120, canvas_top + CANVAS_H + 110, 90, 32)

    dragging_scrubber = False

    def do_generate():
        nonlocal anim_data, current_t, playing, loading, error_msg
        if not input_text.strip():
            return
        loading = True
        error_msg = ""
        # repaint once so the user sees the loading state
        draw(loading_override=True)
        pygame.display.flip()
        try:
            anim_data = fetch_animation(input_text.strip())
            current_t = 0.0
            playing = False
        except Exception as e:
            error_msg = f"Error: {e}"
            anim_data = None
        loading = False

    def draw(loading_override=False):
        screen.fill(BLACK)

        pygame.draw.rect(screen, (30, 30, 55), input_box, border_radius=6)
        pygame.draw.rect(screen, PURPLE if input_active else GRAY, input_box, 2, border_radius=6)
        screen.blit(font_input.render(input_text, True, WHITE), (input_box.x + 8, input_box.y + 6))

        is_loading = loading or loading_override
        gen_color = GRAY if is_loading else PURPLE
        draw_button(screen, generate_btn, "..." if is_loading else "Generate", font_small, gen_color)

        if error_msg:
            for i, line in enumerate(wrap_text(error_msg, font_tiny, WIDTH - 40)[:3]):
                screen.blit(font_tiny.render(line, True, RED), (20, 60 + i * 16))

        if anim_data:
            bg_color = hex_to_rgb(anim_data.get("background", "#e8f0f8"))
            canvas_rect = pygame.Rect(0, canvas_top, WIDTH, CANVAS_H)
            pygame.draw.rect(screen, bg_color, canvas_rect)

            for gx in range(0, WIDTH, 40):
                pygame.draw.line(screen, (0, 0, 0), (gx, canvas_top), (gx, canvas_top + CANVAS_H))
            for gy in range(canvas_top, canvas_top + CANVAS_H, 40):
                pygame.draw.line(screen, (0, 0, 0), (0, gy), (WIDTH, gy))

            sub = screen.subsurface(canvas_rect)
            for obj in anim_data["objects"]:
                draw_object(sub, obj, current_t)

            pygame.draw.rect(screen, PURPLE, canvas_rect, 2)

            screen.blit(font_title.render(anim_data.get("title", ""), True, PURPLE),
                        (20, canvas_top + CANVAS_H + 8))
            dur_surf = font_tiny.render(f"t = {current_t:.2f}s / {anim_data['duration']}s", True, GRAY)
            screen.blit(dur_surf, (WIDTH - dur_surf.get_width() - 20, canvas_top + CANVAS_H + 12))

            exp = get_current_explanation(anim_data["explanations"], current_t)
            for i, line in enumerate(wrap_text("\u25cf " + exp["text"], font_small, WIDTH - 40)[:2]):
                screen.blit(font_small.render(line, True, BLUE), (20, canvas_top + CANVAS_H + 36 + i * 18))

            pygame.draw.rect(screen, (60, 60, 80), scrubber_rect, border_radius=3)
            progress = current_t / anim_data["duration"] if anim_data["duration"] else 0
            fill_rect = pygame.Rect(scrubber_rect.x, scrubber_rect.y,
                                     int(scrubber_rect.width * progress), scrubber_rect.height)
            pygame.draw.rect(screen, PURPLE, fill_rect, border_radius=3)

            handle_x = scrubber_rect.x + int(scrubber_rect.width * progress)
            pygame.draw.circle(screen, WHITE, (handle_x, scrubber_rect.y + 3), 7)
            pygame.draw.circle(screen, PURPLE, (handle_x, scrubber_rect.y + 3), 7, 2)

            for ex in anim_data["explanations"]:
                mx = scrubber_rect.x + int(scrubber_rect.width * (ex["t"] / anim_data["duration"]))
                pygame.draw.circle(screen, GREEN, (mx, scrubber_rect.y + 3), 3)

            draw_button(screen, play_btn, "Pause" if playing else "Play", font_small, BLUE)
            draw_button(screen, reset_btn, "Reset", font_small, (60, 60, 80))

            for i, line in enumerate(wrap_text(anim_data.get("physics_summary", ""), font_tiny, WIDTH - 40)[:3]):
                screen.blit(font_tiny.render(line, True, GREEN), (20, canvas_top + CANVAS_H + 152 + i * 15))

            provider = anim_data.get("_provider", "")
            if provider:
                p_surf = font_tiny.render(f"via {provider}", True, GRAY)
                screen.blit(p_surf, (WIDTH - p_surf.get_width() - 10, HEIGHT - 18))
        else:
            pygame.draw.rect(screen, (15, 15, 30), pygame.Rect(0, canvas_top, WIDTH, CANVAS_H))
            msg_surf = font_small.render("Type a description above and click Generate", True, GRAY)
            screen.blit(msg_surf, msg_surf.get_rect(center=(WIDTH // 2, canvas_top + CANVAS_H // 2)))

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN and input_active:
                if event.key == pygame.K_RETURN:
                    do_generate()
                elif event.key == pygame.K_BACKSPACE:
                    input_text = input_text[:-1]
                elif event.key == pygame.K_ESCAPE:
                    input_active = False
                else:
                    if len(input_text) < 120:
                        input_text += event.unicode

            elif event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                input_active = input_box.collidepoint(mx, my)

                if generate_btn.collidepoint(mx, my):
                    do_generate()

                if anim_data:
                    if play_btn.collidepoint(mx, my):
                        if current_t >= anim_data["duration"]:
                            current_t = 0
                        playing = not playing
                    if reset_btn.collidepoint(mx, my):
                        playing = False
                        current_t = 0
                    if scrubber_rect.collidepoint(mx, my):
                        dragging_scrubber = True
                        playing = False
                        rel = (mx - scrubber_rect.x) / scrubber_rect.width
                        current_t = max(0, min(1, rel)) * anim_data["duration"]

            elif event.type == pygame.MOUSEBUTTONUP:
                dragging_scrubber = False

            elif event.type == pygame.MOUSEMOTION and dragging_scrubber and anim_data:
                mx, _ = event.pos
                rel = (mx - scrubber_rect.x) / scrubber_rect.width
                current_t = max(0, min(1, rel)) * anim_data["duration"]

        if anim_data and playing:
            current_t += dt
            if current_t >= anim_data["duration"]:
                current_t = anim_data["duration"]
                playing = False

        draw()
        pygame.display.flip()

    pygame.quit()


# ════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    print("FastAPI backend running on http://127.0.0.1:8000  (Pygame window starting...)")
    run_frontend()
    sys.exit(0)
