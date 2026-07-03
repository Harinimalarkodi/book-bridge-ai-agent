# 📚 Book Bridge Platform

A simple Flask web app that connects people who have books they no longer
need with people who want to borrow or collect them.

Built as a beginner-friendly college mini project using:

- Python Flask
- HTML5 / CSS3
- Bootstrap 5
- JavaScript
- Mongo DB

## Features

- **Home Page** – quick overview, stats, and recently added books
- **Add Book** – form to list a book with owner contact details (login required)
- **View All Books** – browse every book listed on the platform
- **Search Books** – filter by title, author, or category
- **Owner Contact Display** – see the owner's full Name, Email, and Phone Number
- **Contact Owner button** – one click opens an email to the owner
- **User Registration / Login / Logout** – accounts with hashed passwords
- **Owner-only Delete** – only the logged-in user who added a book can remove it
- **SQLite Database** – created automatically the first time you run the app
- **Responsive UI** – built with Bootstrap 5, works on mobile and desktop

No payment gateway, chat, or admin panel — kept intentionally simple.

### Accounts & Contact Details (New)

- Visitors must **register** (Name, Email, Phone, Password) and **login**
  before they can add a book. Passwords are hashed with Werkzeug's
  `generate_password_hash` — never stored in plain text.
- Each book listing is linked to the account that added it, so the
  **View Books** page can show the owner's complete registered contact
  details (Name, Email, Phone) along with a **Contact Owner** button
  (opens a `mailto:` link).
- The **Remove Listing** button only appears for the logged-in user who
  owns that particular book — no one else can delete it (enforced on
  the server too, not just hidden in the UI).
- Book listings added before this update (with no linked account) still
  display normally using their original owner name/contact fields.

## Folder Structure

```
BookBridge/
│
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── README.md               # This file
├── database.db             # SQLite database (auto-created on first run)
│
├── templates/
│   ├── index.html          # Home page
│   ├── add_book.html       # Add Book form
│   └── books.html          # View / Search Books page
│
└── static/
    ├── style.css            # Custom styling
    └── script.js            # Client-side validation & UX
```

## Setup Instructions

1. **Extract the ZIP file** and open a terminal inside the `BookBridge` folder.

2. **(Recommended) Create a virtual environment:**

   ```bash
   python -m venv venv
   ```

   Activate it:

   - Windows: `venv\Scripts\activate`
   - macOS / Linux: `source venv/bin/activate`

3. **Install the dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application:**

   ```bash
   python app.py
   ```

5. **Open your browser** and go to:

   ```
   http://127.0.0.1:5000
   ```

That's it! The SQLite database (`database.db`) is created automatically the
first time the app runs, so there's no manual database setup required.

## How It Works

- `app.py` sets up Flask routes for the home page, adding books, and
  viewing/searching books. It uses `sqlite3` directly (no ORM) to keep
  things simple and easy to understand.
- Jinja2 templates (`templates/*.html`) render dynamic content, such as
  the list of books and search results, using Bootstrap 5 for styling.
- `static/script.js` adds simple client-side form validation and
  auto-dismissing flash messages.
- All book data (title, author, category, description, owner name, and
  owner contact) is stored in the `books` table inside `database.db`.

## Possible Future Improvements

- User accounts / login
- Book cover image uploads
- Messaging system between users
- Pagination for large numbers of listings

## License

This project is provided for educational purposes as a college mini project.
Feel free to modify and reuse it.

## ChromaDB Vector Database (New — RAG for the Library Assistant Agent)

The **AI Assistant** (`/ai-assistant`) now uses **Retrieval Augmented
Generation (RAG)**: before asking Groq to answer, it retrieves the
most relevant books from a local **ChromaDB** vector database and
passes them to Groq as context.

```
BookBridge/
├── ai/
│   ├── __init__.py
│   ├── groq_assistant.py       # now retrieves context via vector_store, then calls Groq
│   └── vector_store.py          # NEW: ChromaDB integration
├── chroma_db/                    # NEW: local vector store data (auto-created, gitignored)
```

- **How it stays in sync automatically:**
  - On app startup, all books already in SQLite are embedded into
    ChromaDB (`vector_store.sync_all_books_from_sqlite()`), so nothing
    needs to be done manually the first time you run the project.
  - When a book is **added**, it's immediately embedded and upserted
    into ChromaDB.
  - When a book is **deleted**, its embedding is immediately removed
    from ChromaDB.
- **How retrieval works:** when a user asks the AI Assistant a
  question, up to 3 of the most relevant books are retrieved from
  ChromaDB and included as context before Groq generates its answer
  — this grounds recommendations and availability answers in books
  that actually exist on Book Bridge.
- **Storage:** ChromaDB persists locally to the `chroma_db/` folder —
  no external vector database service is required. This folder is
  auto-created and excluded via `.gitignore`.
- **New dependency:** `chromadb` was added to `requirements.txt`.
  Install with:
  ```
  pip install -r requirements.txt
  ```
- All of this is isolated to the `ai/` module — Login, Register, Add
  Book, Search, Contact Owner, Delete Book, the SQLite database, and
  every other existing feature/page are unchanged.

A **Groq-powered AI Assistant** chatbot has been added for the
**Library Assistant Agent** (Smart Campus / College domain):

```
BookBridge/
├── ai/
│   ├── __init__.py
│   └── groq_assistant.py       # Groq API wrapper: ask_library_assistant()
├── templates/
│   └── ai_chat.html             # New "AI Assistant" chatbot page
├── .env                          # Stores GROQ_API_KEY (not committed to git)
```

- **New nav button "AI Assistant"** → `/ai-assistant` — a clean chatbot
  page that talks to Groq via `ai/groq_assistant.py`
  (`ask_library_assistant()`), sent to the backend via `/ai-assistant/chat`.
- The assistant is grounded with a carefully engineered system prompt
  that describes exactly how Book Bridge works (registration, login,
  adding a book, searching, contacting an owner, categories) so its
  answers match the real app. It can also recommend books/genres based
  on a user's stated interests.
- It's restricted to Book Bridge, library, and book-related questions
  only — anything off-topic gets a polite redirect back to those topics.
- The **original rule-based "Ask AI" page** (`/ask-ai`, predefined
  answers, no external API) is completely unchanged and still works
  exactly as before — the two AI features are independent.
- To activate the Groq Assistant, set your real key in `.env`:
  ```
  GROQ_API_KEY=your_actual_api_key_here
  ```
- Dependencies (`python-dotenv`, `groq`) were already
  added to `requirements.txt`. Install with:
  ```
  pip install -r requirements.txt
  ```
