# Physics Animator

Describe a physical event → get an interactive, time-scrollable animation with explanations.

```
physics-animator/
├── backend/
│   ├── main.py           ← FastAPI app + Claude API
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    └── index.html        ← Single-file UI, no build step
```

---

## 1 — Get a free Anthropic API key

1. Go to https://console.anthropic.com and sign up (free tier available)
2. Create an API key

---

## 2 — Set up the backend

```bash
cd backend

# Create a virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set your API key
cp .env.example .env
# Edit .env and paste your key:  ANTHROPIC_API_KEY=sk-ant-...

# Run the server
uvicorn main:app --reload
```

The API will be live at http://localhost:8000
You can test it at http://localhost:8000/docs (Swagger UI)

---

## 3 — Open the frontend

Just open `frontend/index.html` directly in your browser — no build step, no server needed.

```bash
open frontend/index.html        # macOS
xdg-open frontend/index.html   # Linux
# Windows: double-click the file
```

---

## How it works

1. You type a physical event description
2. The frontend POSTs `{ "description": "..." }` to `POST /generate`
3. FastAPI sends it to Claude with a strict JSON prompt
4. Claude returns keyframe animation data (objects, positions, timings, explanations)
5. The frontend renders it on a Canvas with a time scrubber

---

## API endpoint

**POST** `/generate`

Request body:
```json
{ "description": "A ball rolls off a table and falls to the ground" }
```

Response (example structure):
```json
{
  "title": "Ball Rolling Off Table",
  "duration": 4,
  "background": "#d0e8f0",
  "objects": [...],
  "explanations": [...],
  "physics_summary": "..."
}
```