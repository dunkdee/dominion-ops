import json
import os
from typing import AsyncIterator

import anthropic

try:
    from buddy_core.core.brain_router import _compose_system
except ImportError:
    from core.brain_router import _compose_system


CLIENT = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
ANTHROPIC_MODEL = os.getenv("YOUTUBE_ANTHROPIC_MODEL", "claude-sonnet-4-6")

SYSTEM_PROMPT = """You are an expert Hollywood screenwriter and YouTube filmmaker.
Generate compelling, production-ready content for YouTube films.
Structure all scripts with clear scene headings (INT./EXT.), action lines, and dialogue.
Keep scenes visual and suitable for AI video generation."""


def _system(extra: str | None = None) -> str:
    specialist = SYSTEM_PROMPT if not extra else f"{SYSTEM_PROMPT}\n\n{extra}"
    return _compose_system(specialist)


def generate_script(prompt: str, title: str) -> str:
    """Generate a full governed YouTube film script with streaming."""
    full_text = []
    with CLIENT.messages.stream(
        model=ANTHROPIC_MODEL,
        max_tokens=8000,
        system=_system(),
        messages=[
            {
                "role": "user",
                "content": (
                    f"Write a complete YouTube film script titled '{title}'.\n\n"
                    f"Premise: {prompt}\n\n"
                    "Format the output as:\n"
                    "1. LOGLINE (one sentence)\n"
                    "2. SYNOPSIS (2-3 paragraphs)\n"
                    "3. FULL SCRIPT (proper screenplay format)\n"
                    "4. SCENE BREAKDOWN (JSON list of scenes with: scene_number, "
                    "location, time_of_day, description, dialogue_summary, duration_seconds)"
                ),
            }
        ],
    ) as stream:
        for text in stream.text_stream:
            full_text.append(text)

    return "".join(full_text)


def generate_scene_visuals(scene_description: str) -> str:
    """Generate a detailed governed visual prompt for a single scene."""
    with CLIENT.messages.stream(
        model=ANTHROPIC_MODEL,
        max_tokens=500,
        system=_system("Create visual-generation prompts only; do not claim any image or video was rendered."),
        messages=[
            {
                "role": "user",
                "content": (
                    "Convert this scene description into a detailed visual generation prompt "
                    "for an AI video tool. Be specific about lighting, camera angle, "
                    "mood, and visual style. Keep it under 200 words.\n\n"
                    f"Scene: {scene_description}"
                ),
            }
        ],
    ) as stream:
        return stream.get_final_message().content[0].text


def generate_voiceover(script_text: str) -> str:
    """Extract and polish the narration/voiceover track from a script."""
    with CLIENT.messages.stream(
        model=ANTHROPIC_MODEL,
        max_tokens=4000,
        system=_system("Transform supplied script text into narration; preserve factual uncertainty from the source."),
        messages=[
            {
                "role": "user",
                "content": (
                    "Extract and rewrite only the narration and voiceover text from this script "
                    "as clean, spoken sentences suitable for text-to-speech. "
                    "Include natural pauses marked with '...' and scene markers like [SCENE 1].\n\n"
                    f"{script_text}"
                ),
            }
        ],
    ) as stream:
        return stream.get_final_message().content[0].text


def generate_title_and_description(script_text: str, title: str) -> dict:
    """Generate governed YouTube-optimized title, description, and tags."""
    result = CLIENT.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1000,
        system=_system("Optimize metadata for relevance and clarity without inventing performance claims or metrics."),
        messages=[
            {
                "role": "user",
                "content": (
                    f"Based on this film script titled '{title}', generate:\n"
                    "1. An SEO-optimized YouTube title (max 70 chars)\n"
                    "2. A YouTube description (300-500 words, include timestamps placeholder)\n"
                    "3. 15 relevant YouTube tags\n\n"
                    "Respond in JSON format: {title, description, tags}\n\n"
                    f"Script excerpt:\n{script_text[:3000]}"
                ),
            }
        ],
    )

    text = result.content[0].text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        return json.loads(text[start:end])
    return {"title": title, "description": "", "tags": []}
