"""
ai package
----------
Houses the Groq API integration for Book Bridge's
"Library Assistant Agent" (Smart Campus / College domain).

Used by the new "AI Assistant" chatbot page (route /ai-assistant,
template templates/ai_chat.html). This is separate from the original
rule-based "Ask AI" page (route /ask-ai, template
templates/ai_assistant.html), which is unchanged and keeps using its
own predefined answers.
"""

from .groq_assistant import ask_library_assistant

__all__ = ["ask_library_assistant"]
