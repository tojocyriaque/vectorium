# Vectorium

**AI-Powered Physics Animation & Narration Engine**

Vectorium is an interactive educational tool that transforms natural language descriptions of physics events into real-time, time-synchronized animations. It acts as a digital physics professor, generating motion, physics vectors, LaTeX formulas, and step-by-step narrations from simple text prompts.

## ✨ Features

- **Natural Language to Physics**: Describe an event (e.g., "A ball rolls off a table and bounces") and watch it come to life.
- **Physics Narration Engine**: Explanations, formulas, and emphasis highlights are perfectly synchronized with the physical motion, resembling a live lecture.
- **Vector Rendering**: Real-time rendering of velocity (blue), acceleration (green), and force (red) vectors perfectly timed to physical interactions.
- **Canvas-First UI**: A clean, cinematic, distraction-free "whiteboard" style environment powered by Pygame.
- **Dual AI Backends**: Support for cutting-edge LLMs via Groq (Llama 3) and Google Gemini (Gemini 2.0 Flash) to generate accurate physics JSON schemas.

## 🏗️ Architecture

The system consists of two tightly coupled components:

1. **Backend (`apis.py`)**: A FastAPI server that handles prompt generation, LLM orchestration (Groq/Gemini), and rigorous JSON schema validation. It structures physics events into chronological "teaching moments".
2. **Frontend (`gui.py`)**: A Pygame rendering engine that interpolates motion keyframes, renders floating subtitles and formulas, and manages the interactive playback timeline.

## 🚀 Getting Started

### Prerequisites

- Python 3.9+
- An API key for Groq and/or Google Gemini.

### Installation

1. Clone the repository and navigate to the project directory:
   ```bash
   cd vectorium
   ```

2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   *(Note: Ensure you are using `pygame-ce` for the best performance and compatibility).*

3. Create a `.env` file in the root directory and add your API keys:
   ```env
   GROQ_API_KEY=your_groq_api_key_here
   GEMINI_API_KEY=your_gemini_api_key_here
   ```

### Running the Application

1. **Start the FastAPI Backend**:
   In your terminal, run the following command to start the backend server on `http://127.0.0.1:8000`:
   ```bash
   python -m uvicorn apis:app --reload
   ```

2. **Launch the Pygame Frontend**:
   In a separate terminal, launch the GUI:
   ```bash
   python gui.py
   ```

3. **Generate an Animation**:
   In the Pygame window, type a physical event description into the bottom chat bar (e.g., "A pendulum swings back and forth losing energy") and hit Enter to watch the narration engine generate the scene.

## 🔮 Future Roadmap

- **Audio Narration**: Integration with Text-to-Speech (TTS) models for real-time voice narration.
- **3D Physics**: Transitioning from 2D canvas planes to 3D interactive environments.
- **Interactive Quizzing**: Allowing the simulation to pause and prompt the user with conceptual physics questions.
