"""
Tests for chatbot/app.py
Mocks both gradio and anthropic so no real network calls are made.
"""
import sys
import types
import importlib
from unittest.mock import MagicMock, patch, mock_open
import pytest


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

FAKE_KB = "Kumar is awesome. He worked at Hiver as VP Engineering."

FAKE_RESPONSE_TEXT = "Kumar led several transformations at Hiver."


def _build_fake_response(text: str = FAKE_RESPONSE_TEXT):
    """Build a minimal object that mimics anthropic.types.Message."""
    content_block = MagicMock()
    content_block.text = text
    msg = MagicMock()
    msg.content = [content_block]
    return msg


@pytest.fixture(autouse=True)
def mock_env_api_key(monkeypatch):
    """Ensure ANTHROPIC_API_KEY is always set so the module can be imported."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-12345")


@pytest.fixture()
def app_module(monkeypatch, tmp_path):
    """
    Import app.py in isolation each time, mocking:
      - gradio (gr)
      - anthropic
      - the open() call that reads knowledge_base.md
    Returns the imported module.
    """
    # Patch builtins.open so the kb file read doesn't hit disk
    # (but still allow other opens to work normally)
    original_open = open

    def patched_open(file, *args, **kwargs):
        if "knowledge_base.md" in str(file):
            import io
            return io.StringIO(FAKE_KB)
        return original_open(file, *args, **kwargs)

    # Build mock gradio module
    gr_mock = MagicMock()
    gr_mock.ChatInterface = MagicMock(return_value=MagicMock())
    gr_mock.themes = MagicMock()
    gr_mock.themes.Soft = MagicMock(return_value=MagicMock())

    # Build mock anthropic module
    anthropic_mock = MagicMock()
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _build_fake_response()
    anthropic_mock.Anthropic.return_value = fake_client

    with patch("builtins.open", side_effect=patched_open):
        with patch.dict(sys.modules, {"gradio": gr_mock, "anthropic": anthropic_mock}):
            # Remove cached version of app so it's re-imported fresh
            sys.modules.pop("app", None)
            import importlib.util, os
            spec = importlib.util.spec_from_file_location(
                "app",
                "/Users/kumarshailove/gh.kumarshailove/claude-forge/projects/mywebsite/chatbot/app.py",
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules["app"] = module
            spec.loader.exec_module(module)
            yield module
            # Cleanup
            sys.modules.pop("app", None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestModuleConstants:
    def test_knowledge_base_is_loaded(self, app_module):
        assert FAKE_KB in app_module.SYSTEM_PROMPT

    def test_system_prompt_contains_knowledge_base_section(self, app_module):
        assert "KNOWLEDGE BASE:" in app_module.SYSTEM_PROMPT

    def test_system_prompt_is_non_empty(self, app_module):
        assert len(app_module.SYSTEM_PROMPT) > 0

    def test_client_is_initialized(self, app_module):
        assert app_module.client is not None

    def test_demo_is_created(self, app_module):
        assert app_module.demo is not None


class TestChatFunction:
    def test_chat_returns_string(self, app_module):
        result = app_module.chat("Hello", [])
        assert isinstance(result, str)

    def test_chat_returns_expected_text(self, app_module):
        result = app_module.chat("What did Kumar do?", [])
        assert result == FAKE_RESPONSE_TEXT

    def test_chat_passes_user_message(self, app_module):
        app_module.chat("Test message", [])
        call_kwargs = app_module.client.messages.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages") or call_kwargs[0][2]
        user_msgs = [m for m in messages if m["role"] == "user"]
        assert any("Test message" in m["content"] for m in user_msgs)

    def test_chat_includes_history_in_messages(self, app_module):
        history = [
            {"role": "user", "content": "previous question"},
            {"role": "assistant", "content": "previous answer"},
        ]
        app_module.chat("follow-up", history)
        call_kwargs = app_module.client.messages.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages") or call_kwargs[0][2]
        assert len(messages) == 3  # 2 history + 1 new

    def test_chat_passes_system_prompt(self, app_module):
        app_module.chat("Hi", [])
        call_kwargs = app_module.client.messages.create.call_args
        system = call_kwargs.kwargs.get("system") or call_kwargs[1].get("system")
        assert system == app_module.SYSTEM_PROMPT

    def test_chat_uses_correct_model(self, app_module):
        app_module.chat("Hi", [])
        call_kwargs = app_module.client.messages.create.call_args
        model = call_kwargs.kwargs.get("model") or call_kwargs[1].get("model")
        assert model == "claude-sonnet-4-6"

    def test_chat_with_empty_history(self, app_module):
        result = app_module.chat("Hello", [])
        assert result is not None

    def test_chat_with_multi_turn_history(self, app_module):
        history = [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "q2"},
            {"role": "assistant", "content": "a2"},
        ]
        result = app_module.chat("q3", history)
        assert isinstance(result, str)


class TestGradioSetup:
    def test_gradio_chat_interface_created(self, app_module):
        # Verify that gr.ChatInterface was called during module load
        import sys
        gr = sys.modules["gradio"]
        gr.ChatInterface.assert_called_once()

    def test_gradio_chat_interface_fn_is_chat(self, app_module):
        import sys
        gr = sys.modules["gradio"]
        call_kwargs = gr.ChatInterface.call_args
        fn = call_kwargs.kwargs.get("fn") or call_kwargs[0][0]
        assert fn == app_module.chat
