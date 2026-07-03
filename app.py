"""
Book Bridge Platform
---------------------
A simple Flask web app where users can list books they no longer need,
and other users can search for books and view the owner's contact info
to arrange borrowing/collection.

No login, payment, chat, or admin panel — kept intentionally simple
for a college mini project.
"""

from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, timezone
import os

from dotenv import load_dotenv
from pymongo import MongoClient
from bson.objectid import ObjectId
from bson.errors import InvalidId

# NEW: Groq-powered Library Assistant Agent (separate ai/ module)
from ai.groq_assistant import ask_library_assistant

# NEW: ChromaDB vector store, kept in sync with the books collection (RAG)
from ai import vector_store

load_dotenv()

app = Flask(__name__)
app.secret_key = "book_bridge_secret_key"  # needed for flash messages + sessions


# ---------------------------------------------------------------------------
# DATABASE HELPERS
# ---------------------------------------------------------------------------

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "book_bridge")

_mongo_client = None
_db = None


def get_db():
    """Create (once) and return the MongoDB Atlas database handle.
    Uses a single cached MongoClient for the lifetime of the app, which
    is the recommended PyMongo usage pattern (it manages its own
    connection pool internally).
    """
    global _mongo_client, _db
    if _db is None:
        _mongo_client = MongoClient(MONGO_URI)
        _db = _mongo_client[MONGO_DB_NAME]
    return _db


def init_db():
    """Ensure the required indexes exist. MongoDB creates collections
    automatically on first insert, so there's no schema to create up
    front — this just mirrors the old sqlite init_db()'s job of making
    sure the database is ready to use (e.g. enforcing unique emails).
    """
    db = get_db()
    db.users.create_index("email", unique=True)


def _serialize_book(doc, reg_user=None):
    """Convert a MongoDB book document into a plain dict the templates
    can use exactly like they used sqlite3.Row before (book['field']),
    including the same 'reg_name'/'reg_email'/'reg_phone' keys that used
    to come from the SQLite LEFT JOIN with users.
    """
    book = {
        "id": str(doc["_id"]),
        "title": doc.get("title"),
        "author": doc.get("author"),
        "category": doc.get("category"),
        "description": doc.get("description"),
        "owner_name": doc.get("owner_name"),
        "owner_contact": doc.get("owner_contact"),
        "user_id": doc.get("user_id"),
        "date_added": doc.get("date_added"),
        "reg_name": None,
        "reg_email": None,
        "reg_phone": None,
    }
    if reg_user:
        book["reg_name"] = reg_user.get("name")
        book["reg_email"] = reg_user.get("email")
        book["reg_phone"] = reg_user.get("phone")
    return book


def login_required(view_func):
    """Simple decorator to require a logged-in user for a route."""
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login to continue.", "warning")
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)
    return wrapped


# ---------------------------------------------------------------------------
# AI BOOK ASSISTANT (NEW): simple rule-based Q&A, no external AI service.
# Answers are 100% predefined below and matched using basic keyword checks.
# ---------------------------------------------------------------------------

AI_FALLBACK_ANSWER = "Sorry, I can only answer questions related to the Book Bridge platform."

# Each entry: (list of keywords/phrases to look for in the question, answer text)
AI_KNOWLEDGE_BASE = [
    (
        ["what is book bridge", "about book bridge", "what is this"],
        "Book Bridge is a simple platform where people who have books they no longer "
        "need can list them, and others can search for books and contact the owner "
        "to borrow or collect them.",
    ),
    (
        ["register", "sign up", "signup", "create account", "create an account"],
        "To register, click 'Register' in the navigation bar, then fill in your "
        "Name, Email, Phone Number, and Password. Once registered, you can login "
        "and start adding books.",
    ),
    (
        ["login", "log in", "sign in"],
        "To login, click 'Login' in the navigation bar and enter the email and "
        "password you used when registering.",
    ),
    (
        ["add a book", "add book", "list a book", "how do i add"],
        "To add a book, first login to your account, then click 'Add Book' in the "
        "navigation bar and fill in the book's title, author, category, description, "
        "and your contact details.",
    ),
    (
        ["search", "find a book", "find book", "browse"],
        "To search for books, go to the 'View Books' page and use the search box "
        "to look up books by title, author, or category.",
    ),
    (
        ["contact the owner", "contact owner", "reach the owner", "contact a book owner"],
        "On the 'View Books' page, each book listing shows the owner's Name, Email, "
        "and Phone Number. You can click the 'Contact Owner' button to open a "
        "pre-filled Gmail compose window and email them directly.",
    ),
    (
        ["categories", "category", "what kind of books", "types of books"],
        "Book Bridge supports these categories: Fiction, Non-Fiction, Academic, "
        "Children, Biography, Science, and Other.",
    ),
]


def get_ai_response(question):
    """Match the user's question against the predefined knowledge base
    using simple keyword matching. Returns the fallback message if no
    predefined topic matches. This is intentionally simple/rule-based —
    no external AI service (OpenAI, Groq, etc.) is used.
    """
    if not question:
        return AI_FALLBACK_ANSWER

    normalized = question.lower().strip()

    for keywords, answer in AI_KNOWLEDGE_BASE:
        for keyword in keywords:
            if keyword in normalized:
                return answer

    return AI_FALLBACK_ANSWER


# ---------------------------------------------------------------------------
# ROUTES
# ---------------------------------------------------------------------------

@app.route("/")
def home():
    """Home page with a short intro and quick stats."""
    db = get_db()
    total_books = db.books.count_documents({})
    recent_docs = db.books.find().sort("_id", -1).limit(3)
    recent_books = [_serialize_book(doc) for doc in recent_docs]
    return render_template("index.html", total_books=total_books, recent_books=recent_books)


@app.route("/add", methods=["GET", "POST"])
@login_required
def add_book():
    """Show the Add Book form (GET) and save a new book (POST).
    NEW: requires login, and the new listing is linked to the logged-in
    user's account (session['user_id']) so their registered Name/Email/
    Phone can be shown as complete owner contact details, and so only
    they can delete it later.
    """
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        author = request.form.get("author", "").strip()
        category = request.form.get("category", "").strip()
        description = request.form.get("description", "").strip()
        owner_name = request.form.get("owner_name", "").strip()
        owner_contact = request.form.get("owner_contact", "").strip()

        # Basic server-side validation
        if not (title and author and category and owner_name and owner_contact):
            flash("Please fill in all required fields.", "danger")
            return redirect(url_for("add_book"))

        db = get_db()
        result = db.books.insert_one(
            {
                "title": title,
                "author": author,
                "category": category,
                "description": description,
                "owner_name": owner_name,
                "owner_contact": owner_contact,
                "user_id": session["user_id"],
                "date_added": datetime.now(timezone.utc).isoformat(),
            }
        )
        new_book_id = str(result.inserted_id)

        # NEW: keep ChromaDB in sync — embed the newly added book so the
        # AI Assistant can retrieve it for future questions/recommendations.
        try:
            vector_store.upsert_book(
                {
                    "id": new_book_id,
                    "title": title,
                    "author": author,
                    "category": category,
                    "description": description,
                    "owner_name": owner_name,
                    "owner_contact": owner_contact,
                }
            )
        except Exception:
            pass  # ChromaDB sync issues should never block adding a book

        flash("Book added successfully!", "success")
        return redirect(url_for("view_books"))

    return render_template("add_book.html")


@app.route("/books")
def view_books():
    """Display all books, optionally filtered by a search query."""
    query = request.args.get("q", "").strip()

    db = get_db()

    if query:
        # Case-insensitive partial match on title/author/category —
        # equivalent to the old "LIKE %query%" SQL search.
        pattern = {"$regex": query, "$options": "i"}
        mongo_filter = {"$or": [{"title": pattern}, {"author": pattern}, {"category": pattern}]}
    else:
        mongo_filter = {}

    book_docs = list(db.books.find(mongo_filter).sort("_id", -1))

    # NEW: fetch registered owner details for every book that has a
    # user_id, equivalent to the old SQLite LEFT JOIN with users — so
    # complete owner contact info (Name, Email, Phone) can be shown.
    # Legacy books with no user_id simply fall back to their original
    # owner_name/owner_contact, exactly as before.
    user_ids = {doc["user_id"] for doc in book_docs if doc.get("user_id")}
    users_by_id = {}
    if user_ids:
        object_ids = []
        for uid in user_ids:
            try:
                object_ids.append(ObjectId(uid))
            except (InvalidId, TypeError):
                continue
        for user_doc in db.users.find({"_id": {"$in": object_ids}}):
            users_by_id[str(user_doc["_id"])] = user_doc

    books = [
        _serialize_book(doc, users_by_id.get(doc.get("user_id")))
        for doc in book_docs
    ]

    return render_template("books.html", books=books, query=query)


@app.route("/delete/<book_id>")
@login_required
def delete_book(book_id):
    """Remove a book listing (e.g. once it has been given away).
    NEW: only the logged-in user who owns this listing may delete it.
    """
    db = get_db()

    try:
        object_id = ObjectId(book_id)
    except (InvalidId, TypeError):
        flash("Book listing not found.", "danger")
        return redirect(url_for("view_books"))

    book = db.books.find_one({"_id": object_id})

    if book is None:
        flash("Book listing not found.", "danger")
        return redirect(url_for("view_books"))

    if book.get("user_id") != session.get("user_id"):
        flash("You can only delete your own book listings.", "danger")
        return redirect(url_for("view_books"))

    db.books.delete_one({"_id": object_id})

    # NEW: keep ChromaDB in sync — remove the deleted book's embedding.
    try:
        vector_store.delete_book(book_id)
    except Exception:
        pass  # ChromaDB sync issues should never block deleting a book

    flash("Book listing removed.", "info")
    return redirect(url_for("view_books"))


# ---------------------------------------------------------------------------
# AUTH ROUTES (NEW): Registration / Login / Logout
# ---------------------------------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register a new user account. Password is hashed before storage."""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not (name and email and phone and password and confirm_password):
            flash("Please fill in all fields.", "danger")
            return redirect(url_for("register"))

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("register"))

        db = get_db()
        existing = db.users.find_one({"email": email})
        if existing:
            flash("An account with that email already exists. Please login.", "warning")
            return redirect(url_for("login"))

        password_hash = generate_password_hash(password)
        db.users.insert_one(
            {
                "name": name,
                "email": email,
                "phone": phone,
                "password_hash": password_hash,
                "date_joined": datetime.now(timezone.utc).isoformat(),
            }
        )

        flash("Registration successful! Please login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log a user in by verifying their hashed password."""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        db = get_db()
        user = db.users.find_one({"email": email})

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = str(user["_id"])
            session["user_name"] = user["name"]
            flash(f"Welcome back, {user['name']}!", "success")
            return redirect(url_for("home"))

        flash("Invalid email or password.", "danger")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    """Log the current user out by clearing their session."""
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("home"))


# ---------------------------------------------------------------------------
# AI ASSISTANT ROUTES (NEW)
# ---------------------------------------------------------------------------

@app.route("/ask-ai")
def ask_ai():
    """Render the AI Book Assistant page."""
    return render_template("ai_assistant.html")


@app.route("/ai-response", methods=["POST"])
def ai_response():
    """Return a predefined answer for the user's question as JSON.
    Rule-based only — no external AI service is called.
    """
    question = request.form.get("question", "")
    answer = get_ai_response(question)
    return {"answer": answer}


# ---------------------------------------------------------------------------
# NEW: GROQ-POWERED "AI ASSISTANT" ROUTES (Library Assistant Agent)
# Separate from the rule-based /ask-ai page above, which is unchanged.
# ---------------------------------------------------------------------------

@app.route("/ai-assistant")
def ai_assistant_page():
    """Render the Groq-powered AI Assistant (Library Assistant Agent) page."""
    return render_template("ai_chat.html")


@app.route("/ai-assistant/chat", methods=["POST"])
def ai_assistant_chat():
    """Send the user's question to the Groq Library Assistant Agent
    and return its response as JSON.
    """
    question = request.form.get("question", "")
    answer = ask_library_assistant(question)
    return {"answer": answer}


# ---------------------------------------------------------------------------
# APP ENTRY POINT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Ensure MongoDB indexes exist (safe/idempotent to call every run)
    init_db()

    # NEW: keep ChromaDB in sync with MongoDB Atlas on startup (idempotent
    # upsert), so every existing book is embedded and searchable by the
    # AI Assistant.
    try:
        all_books = [_serialize_book(doc) for doc in get_db().books.find()]
        vector_store.sync_all_books(all_books)
    except Exception:
        pass  # ChromaDB sync issues should never prevent the app from starting

    app.run(debug=True)
