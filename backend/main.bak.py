from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import anthropic
import json
import os

from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Physics Animator API")

# Allow frontend (any origin during dev; tighten in production)
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


@app.get("/")
def root():
    return {"status": "Physics Animator API is running"}


@app.post("/generate")
def generate_animation(req: AnimationRequest):
    print("API key: ", os.getenv("ANTHROPIC_API_KEY"))

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not set in environment")

    client = anthropic.Anthropic(api_key=api_key)

    try:
        message = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": req.description}
            ]
        )

        raw = message.content[0].text
        # Strip any accidental markdown fences
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        clean = clean.strip().rstrip("`").strip()

        animation_data = json.loads(clean)
        return animation_data

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Claude returned invalid JSON: {str(e)}")
    except anthropic.APIError as e:
        raise HTTPException(status_code=502, detail=f"Anthropic API error: {str(e)}")