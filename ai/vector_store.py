"""
ChromaDB Vector Store - Book Bridge Library Assistant Agent
--------------------------------------------------------------
Domain: Smart Campus / College

This module is a separate, self-contained integration with ChromaDB
(a local vector database). It stores an embedding for every book
currently in MongoDB Atlas's `books` collection so the Library
Assistant Agent can retrieve the most relevant books for a user's
question before asking Groq to answer (Retrieval Augmented Generation
/ RAG).

This file does NOT touch the MongoDB data, the Flask routes, or any
existing page — it only receives plain book dicts from app.py. It is
only imported by:
- ai/groq_assistant.py    (to retrieve context before calling Groq)
- app.py                  (to keep the index in sync: sync on startup
                            from MongoDB, upsert when a book is added,
                            delete when a book is removed)

Storage:
ChromaDB persists its data locally to the `chroma_db/` folder inside
the project (created automatically on first use) — no external vector
database service is required.
"""

import chromadb

CHROMA_PERSIST_DIR = "chroma_db"  # local folder for ChromaDB's storage
COLLECTION_NAME = "books"

_client = None
_collection = None


def _get_collection():
    """Lazily create (once) and return the ChromaDB 'books' collection."""
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        _collection = _client.get_or_create_collection(name=COLLECTION_NAME)
    return _collection


def _book_to_document(book):
    """Build the text that gets embedded for a book (used for similarity search)."""
    description = book["description"] or "No description provided."
    return (
        f"Title: {book['title']}. Author: {book['author']}. "
        f"Category: {book['category']}. Description: {description}"
    )


def _book_to_metadata(book):
    """Metadata returned alongside search results (used as Groq context)."""
    return {
        "title": book["title"],
        "author": book["author"],
        "category": book["category"],
        "description": book["description"] or "",
        "owner_name": book["owner_name"],
        "owner_contact": book["owner_contact"],
    }


def upsert_book(book):
    """Add or update a single book's embedding in ChromaDB.
    `book` may be a sqlite3.Row or a plain dict with the standard
    book fields (id, title, author, category, description, owner_name,
    owner_contact).
    """
    collection = _get_collection()
    collection.upsert(
        ids=[str(book["id"])],
        documents=[_book_to_document(book)],
        metadatas=[_book_to_metadata(book)],
    )


def delete_book(book_id):
    """Remove a book's embedding from ChromaDB (called after SQLite delete)."""
    collection = _get_collection()
    try:
        collection.delete(ids=[str(book_id)])
    except Exception:
        pass  # nothing to delete / already removed — safe to ignore


def sync_all_books(books):
    """Rebuild the ChromaDB index from a list of book dicts (fetched by
    app.py from MongoDB Atlas). Upsert is idempotent, so this is safe to
    call every time the app starts (keeps ChromaDB consistent with the
    database even if it was ever out of sync, e.g. after copying the
    project to a new machine).

    `books` is a list of dicts with the standard book fields (id, title,
    author, category, description, owner_name, owner_contact) — the
    same shape app.py already builds for the templates.
    """
    if not books:
        return

    collection = _get_collection()
    collection.upsert(
        ids=[str(b["id"]) for b in books],
        documents=[_book_to_document(b) for b in books],
        metadatas=[_book_to_metadata(b) for b in books],
    )


def search_similar_books(query, n_results=3):
    """Return up to `n_results` books most relevant to `query` as a list
    of metadata dicts (title, author, category, description, owner_name,
    owner_contact). Returns an empty list if ChromaDB has no books yet
    or the query is empty — callers should treat that as "no context".
    """
    if not query or not query.strip():
        return []

    collection = _get_collection()
    count = collection.count()
    if count == 0:
        return []

    results = collection.query(query_texts=[query], n_results=min(n_results, count))
    metadatas = results.get("metadatas", [[]])[0]
    return metadatas
