"""
Groq Integration - Library Assistant Agent
-------------------------------------------
Domain: Smart Campus / College
Agent:  Library Assistant Agent for the Book Bridge platform

This module wraps the Groq API (OpenAI-compatible chat completions) in
a small, self-contained interface. It is kept completely separate from
app.py's core Book Bridge logic (books, users, auth) so none of those
existing routes, pages, or features are touched by this file.

This module is used by the "AI Assistant" page (route /ai-assistant,
template templates/ai_chat.html). It is entirely separate from the
original rule-based "Ask AI" page (route /ask-ai, template
templates/ai_assistant.html), which is untouched and keeps using its
own predefined answers.

RAG (Retrieval Augmented Generation): before asking Groq to answer,
this module retrieves the most relevant books from the ChromaDB vector
store (ai/vector_store.py) and passes them to Groq as context. This
keeps the assistant grounded in books that actually exist on Book
Bridge rather than guessing.

Setup:
1. Add your key to the .env file in the project root:
       GROQ_API_KEY=your_actual_api_key_here
2. Install the dependencies already listed in requirements.txt:
       pip install -r requirements.txt
"""

import os
from dotenv import load_dotenv
from groq import Groq

from . import vector_store  # ChromaDB retrieval (RAG)

# Load variables from the .env file (GROQ_API_KEY, GROQ_MODEL, etc.)
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# ---------------------------------------------------------------------------
# PROMPT ENGINEERING
# ---------------------------------------------------------------------------
# The system instruction below grounds Groq in exactly how Book Bridge
# works (so its answers match the real app, not guesses), and explicitly
# constrains it to Book Bridge / library / book-related topics only.
# ---------------------------------------------------------------------------

OUT_OF_SCOPE_REPLY = (
    "I'm the Book Bridge Library Assistant, so I can only help with "
    "Book Bridge, library, and book-related questions — things like "
    "registering, logging in, adding or searching for books, contacting "
    "an owner, or getting a book recommendation. Could you ask me "
    "something along those lines?"
)

LIBRARY_ASSISTANT_SYSTEM_INSTRUCTION = f"""
You are the "Library Assistant Agent" — an AI assistant embedded in
Book Bridge, a Smart Campus / College book-sharing platform. You speak
directly to students and staff using the platform.

WHAT BOOK BRIDGE IS:
Book Bridge lets users who have books they no longer need list them, so
other users can search for those books and contact the owner to borrow
or collect them. It is free to use and has no payment gateway.

HOW THE PLATFORM WORKS (use this exact information when explaining steps):
1. Register: click "Register" in the navbar, then enter Full Name,
   Email, Phone Number, and a Password (passwords are securely hashed).
2. Login: click "Login" in the navbar and sign in with your registered
   email and password.
3. Add a Book: you must be logged in first. Click "Add Book" in the
   navbar, then fill in Title, Author, Category, Description, and your
   contact details (Name and Contact). The book is then linked to your
   account.
4. Search for Books: go to "View Books" and use the search box to filter
   listings by title, author, or category.
5. Contact the Owner: on "View Books", each listing shows the owner's
   Name, Email, and Phone. Click the "Contact Owner" button to open a
   pre-filled Gmail compose window addressed to that owner.
6. Categories available: Fiction, Non-Fiction, Academic, Children,
   Biography, Science, and Other.
7. Only the logged-in user who added a listing can remove it, using the
   "Remove Listing" button.

YOUR JOB:
- Explain what Book Bridge is when asked.
- Help users understand how to register and login.
- Guide users step-by-step on how to add a book.
- Help users understand how to search for books.
- Explain how to contact a book owner.
- Recommend books or genres based on a user's stated interests (e.g. if
  they like mystery novels, suggest well-known titles/authors in that
  genre and point them to search for that category or title on Book
  Bridge). You may recommend real, well-known books/authors even if you
  don't know whether Book Bridge currently has them listed — just make
  clear they should search the platform to check availability.
- Keep answers concise, warm, and easy to follow, ideally with short
  steps or bullet points when explaining a process.

STRICT SCOPE RULE:
Only answer questions about Book Bridge, libraries, books, reading, or
book recommendations. If a user asks about anything unrelated (e.g.
general trivia, coding help, weather, politics, math homework, etc.),
do NOT answer it. Instead, politely reply with exactly this message:
"{OUT_OF_SCOPE_REPLY}"
"""

_client = None  # lazily created Groq client instance (cached)


def _get_client():
    """Create (once) and return the configured Groq client."""
    global _client
    if _client is None:
        if not GROQ_API_KEY:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Add it to your .env file "
                "before using the Library Assistant Agent."
            )
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


def _build_context_block(relevant_books):
    """Format retrieved ChromaDB book metadata into a context block for Groq."""
    lines = []
    for book in relevant_books:
        description = book.get("description") or "No description provided."
        lines.append(
            f'- "{book.get("title")}" by {book.get("author")} '
            f'({book.get("category")}): {description} '
            f'Owner: {book.get("owner_name")} ({book.get("owner_contact")})'
        )
    return (
        "Here are some books currently listed on Book Bridge that may be "
        "relevant to the user's question below. Use them when helpful "
        "(e.g. for recommendations or availability), but you don't have "
        "to mention all of them:\n" + "\n".join(lines)
    )


def ask_library_assistant(question: str) -> str:
    """
    Send `question` to the Groq-powered Library Assistant Agent and
    return its text response.

    RAG step: first retrieves the most relevant books from the ChromaDB
    vector store and passes them to Groq as context before generating
    the response, so answers/recommendations are grounded in books that
    actually exist on Book Bridge.

    Returns a friendly error message instead of raising, so the calling
    Flask route can display the result directly without its own
    try/except.
    """
    if not question or not question.strip():
        return "Please ask a question about Book Bridge, books, or the library."

    try:
        client = _get_client()

        # Retrieve relevant books from ChromaDB before generating
        try:
            relevant_books = vector_store.search_similar_books(question, n_results=3)
        except Exception:
            # If ChromaDB isn't available/populated yet, fall back to no context
            # rather than failing the whole request.
            relevant_books = []

        if relevant_books:
            context_block = _build_context_block(relevant_books)
            user_content = f"{context_block}\n\nUser question: {question}"
        else:
            user_content = question

        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": LIBRARY_ASSISTANT_SYSTEM_INSTRUCTION},
                {"role": "user", "content": user_content},
            ],
        )
        return completion.choices[0].message.content
    except Exception as exc:  # network issues, missing/invalid key, etc.
        return f"Library Assistant Agent is currently unavailable: {exc}"
