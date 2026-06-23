import os
import gradio as gr
import anthropic

# Load knowledge base from file
with open("knowledge_base.md", "r") as f:
    KNOWLEDGE_BASE = f.read()

SYSTEM_PROMPT = f"""You are Kumar Shailove's personal AI assistant embedded on his portfolio website.
Answer questions about Kumar's career, philosophy, achievements, and experience.
Be professional, confident, and concise. Speak about Kumar in third person (e.g., "Kumar led...").
Do not make up information not present in the knowledge base.
Keep responses to 200 words or fewer unless the visitor explicitly requests a detailed breakdown.
If asked about something not in the knowledge base, say so clearly rather than guessing.

KNOWLEDGE BASE:
{KNOWLEDGE_BASE}
"""

# Initialize Anthropic client — reads ANTHROPIC_API_KEY from environment
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def chat(message: str, history: list[dict]) -> str:
    """
    Process a chat message and return a response.

    Args:
        message: The user's message
        history: List of previous messages in OpenAI-style dict format
                 [{"role": "user"|"assistant", "content": "..."}]

    Returns:
        The assistant's response string
    """
    # Build messages list from history + new message
    messages = list(history) + [{"role": "user", "content": message}]

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=messages,
    )

    return response.content[0].text


# Gradio ChatInterface configuration
demo = gr.ChatInterface(
    fn=chat,
    title="Ask about Kumar",
    description="I'm Kumar's AI assistant. Ask me anything about his background, philosophy, or experience.",
    theme=gr.themes.Soft(),
    type="messages",  # REQUIRED: use OpenAI-style message dicts, not deprecated tuples
    examples=[
        "What did Kumar accomplish at Hiver?",
        "What is Kumar's leadership philosophy?",
        "Tell me about Kumar's 20-year career.",
    ],
    cache_examples=False,  # Do not cache — each run hits the API
)

if __name__ == "__main__":
    demo.launch()
