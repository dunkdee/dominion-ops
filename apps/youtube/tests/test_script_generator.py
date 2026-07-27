"""
Tests for script_generator.py

Strategy: mock the module-level CLIENT object so no real Anthropic calls are made.
"""
import json
import sys
import os
import pytest
from unittest.mock import MagicMock, patch, PropertyMock


# ---------------------------------------------------------------------------
# Helpers to build convincing Anthropic SDK mock objects
# ---------------------------------------------------------------------------

def _make_stream_context(text_chunks: list[str], final_text: str):
    """
    Return a mock context manager that mimics CLIENT.messages.stream().

    - Iterates `text_chunks` when used as `for text in stream.text_stream`
    - Returns a message whose .content[0].text == final_text from
      stream.get_final_message()
    """
    mock_content = MagicMock()
    mock_content.text = final_text

    mock_final_message = MagicMock()
    mock_final_message.content = [mock_content]

    mock_stream = MagicMock()
    mock_stream.text_stream = iter(text_chunks)
    mock_stream.get_final_message.return_value = mock_final_message

    # Make it work as a context manager
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=mock_stream)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


def _make_create_response(text: str):
    """Return a mock response for CLIENT.messages.create()."""
    mock_content = MagicMock()
    mock_content.text = text

    mock_response = MagicMock()
    mock_response.content = [mock_content]
    return mock_response


# ---------------------------------------------------------------------------
# generate_script
# ---------------------------------------------------------------------------

class TestGenerateScript:
    def test_returns_concatenated_stream_chunks(self):
        import script_generator

        ctx = _make_stream_context(["Hello ", "world", "!"], "Hello world!")
        with patch.object(script_generator.CLIENT.messages, "stream", return_value=ctx):
            result = script_generator.generate_script("a robot love story", "ROBO LOVE")

        assert result == "Hello world!"

    def test_passes_prompt_and_title_in_message(self):
        import script_generator

        ctx = _make_stream_context(["script text"], "script text")
        with patch.object(script_generator.CLIENT.messages, "stream", return_value=ctx) as mock_stream:
            script_generator.generate_script("space adventure", "GALAXY QUEST")

        call_kwargs = mock_stream.call_args[1]
        messages = call_kwargs.get("messages") or mock_stream.call_args[0][0] if mock_stream.call_args[0] else call_kwargs["messages"]
        # Grab messages from whichever arg position it ended up in
        _, kwargs = mock_stream.call_args
        assert "GALAXY QUEST" in kwargs["messages"][0]["content"]
        assert "space adventure" in kwargs["messages"][0]["content"]

    def test_uses_correct_model(self):
        import script_generator

        ctx = _make_stream_context(["x"], "x")
        with patch.object(script_generator.CLIENT.messages, "stream", return_value=ctx) as mock_stream:
            script_generator.generate_script("premise", "title")

        _, kwargs = mock_stream.call_args
        assert kwargs["model"] == "claude-fable-5"

    def test_empty_stream_returns_empty_string(self):
        import script_generator

        ctx = _make_stream_context([], "")
        with patch.object(script_generator.CLIENT.messages, "stream", return_value=ctx):
            result = script_generator.generate_script("x", "y")

        assert result == ""

    def test_multiple_chunks_joined_correctly(self):
        import script_generator

        chunks = ["Scene 1\n", "INT. HOUSE\n", "A hero stands tall."]
        ctx = _make_stream_context(chunks, "".join(chunks))
        with patch.object(script_generator.CLIENT.messages, "stream", return_value=ctx):
            result = script_generator.generate_script("hero story", "HERO")

        assert result == "Scene 1\nINT. HOUSE\nA hero stands tall."


# ---------------------------------------------------------------------------
# generate_scene_visuals
# ---------------------------------------------------------------------------

class TestGenerateSceneVisuals:
    def test_returns_final_message_text(self):
        import script_generator

        ctx = _make_stream_context([], "Cinematic wide-angle shot of a forest at dawn.")
        with patch.object(script_generator.CLIENT.messages, "stream", return_value=ctx):
            result = script_generator.generate_scene_visuals("A hero walks through a misty forest")

        assert result == "Cinematic wide-angle shot of a forest at dawn."

    def test_includes_scene_description_in_request(self):
        import script_generator

        ctx = _make_stream_context([], "prompt")
        with patch.object(script_generator.CLIENT.messages, "stream", return_value=ctx) as mock_stream:
            script_generator.generate_scene_visuals("hero fights dragon")

        _, kwargs = mock_stream.call_args
        assert "hero fights dragon" in kwargs["messages"][0]["content"]

    def test_uses_correct_model(self):
        import script_generator

        ctx = _make_stream_context([], "visual prompt")
        with patch.object(script_generator.CLIENT.messages, "stream", return_value=ctx) as mock_stream:
            script_generator.generate_scene_visuals("scene")

        _, kwargs = mock_stream.call_args
        assert kwargs["model"] == "claude-fable-5"

    def test_empty_description_still_returns_string(self):
        import script_generator

        ctx = _make_stream_context([], "generic visual prompt")
        with patch.object(script_generator.CLIENT.messages, "stream", return_value=ctx):
            result = script_generator.generate_scene_visuals("")

        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# generate_voiceover
# ---------------------------------------------------------------------------

class TestGenerateVoiceover:
    def test_returns_final_message_text(self):
        import script_generator

        ctx = _make_stream_context([], "[SCENE 1] A lone wanderer steps into the sunlight...")
        with patch.object(script_generator.CLIENT.messages, "stream", return_value=ctx):
            result = script_generator.generate_voiceover("FULL SCRIPT TEXT HERE")

        assert result == "[SCENE 1] A lone wanderer steps into the sunlight..."

    def test_includes_script_in_request(self):
        import script_generator

        ctx = _make_stream_context([], "voiceover")
        with patch.object(script_generator.CLIENT.messages, "stream", return_value=ctx) as mock_stream:
            script_generator.generate_voiceover("INT. SPACESHIP - DAY\nNARRATOR: The journey begins.")

        _, kwargs = mock_stream.call_args
        assert "INT. SPACESHIP - DAY" in kwargs["messages"][0]["content"]

    def test_uses_correct_model(self):
        import script_generator

        ctx = _make_stream_context([], "voiceover text")
        with patch.object(script_generator.CLIENT.messages, "stream", return_value=ctx) as mock_stream:
            script_generator.generate_voiceover("script")

        _, kwargs = mock_stream.call_args
        assert kwargs["model"] == "claude-fable-5"


# ---------------------------------------------------------------------------
# generate_title_and_description
# ---------------------------------------------------------------------------

class TestGenerateTitleAndDescription:
    def test_returns_parsed_json_from_response(self):
        import script_generator

        payload = {"title": "Epic Robots", "description": "A tale of metal and heart.", "tags": ["robot", "sci-fi"]}
        response_text = f"Here is the JSON:\n{json.dumps(payload)}\nEnd."
        mock_response = _make_create_response(response_text)

        with patch.object(script_generator.CLIENT.messages, "create", return_value=mock_response):
            result = script_generator.generate_title_and_description("script text", "Robot Movie")

        assert result["title"] == "Epic Robots"
        assert result["description"] == "A tale of metal and heart."
        assert result["tags"] == ["robot", "sci-fi"]

    def test_fallback_when_no_json_in_response(self):
        import script_generator

        mock_response = _make_create_response("Sorry, I cannot provide that right now.")
        with patch.object(script_generator.CLIENT.messages, "create", return_value=mock_response):
            result = script_generator.generate_title_and_description("script", "My Movie")

        assert result == {"title": "My Movie", "description": "", "tags": []}

    def test_uses_correct_model(self):
        import script_generator

        mock_response = _make_create_response("{}")
        with patch.object(script_generator.CLIENT.messages, "create", return_value=mock_response) as mock_create:
            script_generator.generate_title_and_description("script", "title")

        _, kwargs = mock_create.call_args
        assert kwargs["model"] == "claude-fable-5"

    def test_truncates_script_to_3000_chars(self):
        import script_generator

        long_script = "x" * 5000
        mock_response = _make_create_response('{"title":"T","description":"D","tags":[]}')
        with patch.object(script_generator.CLIENT.messages, "create", return_value=mock_response) as mock_create:
            script_generator.generate_title_and_description(long_script, "Test Title")

        _, kwargs = mock_create.call_args
        content = kwargs["messages"][0]["content"]
        # The script excerpt in the prompt should be at most 3000 chars from original
        # (the prompt template wraps it, so just check the total content length is bounded)
        # The script itself is truncated to [:3000] per the source code
        assert long_script[3000:] not in content

    def test_json_with_surrounding_text_parsed_correctly(self):
        import script_generator

        payload = {"title": "Great Film", "description": "desc", "tags": ["tag1"]}
        response_text = f"Sure! Here you go:\n\n```json\n{json.dumps(payload)}\n```"
        mock_response = _make_create_response(response_text)
        with patch.object(script_generator.CLIENT.messages, "create", return_value=mock_response):
            result = script_generator.generate_title_and_description("script", "Film")

        assert result["title"] == "Great Film"

    def test_includes_title_in_request(self):
        import script_generator

        mock_response = _make_create_response('{"title":"T","description":"D","tags":[]}')
        with patch.object(script_generator.CLIENT.messages, "create", return_value=mock_response) as mock_create:
            script_generator.generate_title_and_description("script", "UNIQUE_TITLE_XYZ")

        _, kwargs = mock_create.call_args
        assert "UNIQUE_TITLE_XYZ" in kwargs["messages"][0]["content"]