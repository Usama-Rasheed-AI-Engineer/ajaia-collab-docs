from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT_DIR / "data" / "ajaia_docs.db"


def get_db_path() -> Path:
    configured = os.getenv("DATABASE_PATH", "").strip()
    path = Path(configured) if configured else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                role_label TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content_html TEXT NOT NULL DEFAULT '',
                owner_id INTEGER NOT NULL,
                source_type TEXT NOT NULL DEFAULT 'blank',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (owner_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS document_shares (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                permission TEXT NOT NULL DEFAULT 'edit',
                shared_by_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(document_id, user_id),
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (shared_by_id) REFERENCES users(id)
            );
            """
        )
        seed_if_empty(conn)


def seed_if_empty(conn: sqlite3.Connection) -> None:
    existing_users = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()["cnt"]
    if existing_users > 0:
        return

    now = utc_now()
    users = [
        ("Usama Rasheed", "usama@ajaia.io", "Product Engineer"),
        ("Alex Rivera", "alex@ajaia.io", "Design Lead"),
        ("Sara Chen", "sara@ajaia.io", "Operations Lead"),
    ]
    conn.executemany(
        "INSERT INTO users (name, email, role_label) VALUES (?, ?, ?)",
        users,
    )

    user_map = {
        row["email"]: row["id"]
        for row in conn.execute("SELECT id, email FROM users").fetchall()
    }
    usama_id = user_map["usama@ajaia.io"]
    alex_id = user_map["alex@ajaia.io"]

    sample_docs = [
        (
            "Q4 Product Launch Brief",
            (
                "<h1>Q4 Collaborative Workspace Launch</h1>"
                "<p>This brief outlines our <strong>core MVP priorities</strong> for internal team collaboration.</p>"
                "<h2>Key Deliverables</h2>"
                "<ul>"
                "<li><strong>Rich-Text Authoring:</strong> Support headings, inline emphasis, and structured lists.</li>"
                "<li><em>Document Ingestion:</em> Import existing .txt, .md, and .docx drafts cleanly.</li>"
                "<li><u>Workspace Sharing:</u> Clear distinction between owned and shared documents.</li>"
                "</ul>"
                "<h2>Next Steps</h2>"
                "<ol>"
                "<li>Review scope tradeoffs with engineering.</li>"
                "<li>Validate end-to-end sharing permissions.</li>"
                "</ol>"
            ),
            usama_id,
            "seeded",
            now,
            now,
        ),
        (
            "Engineering Architecture Notes",
            (
                "<h1>Architecture &amp; Tradeoff Decisions</h1>"
                "<p>Built with <strong>FastAPI</strong>, <strong>SQLite</strong>, and <strong>Quill.js</strong> to maximize reliability and iteration speed within a 4-hour delivery window.</p>"
                "<ul>"
                "<li>Single-container deployment with deterministic SQLite persistence.</li>"
                "<li>Server-side HTML sanitization to preserve rich formatting safely.</li>"
                "</ul>"
            ),
            usama_id,
            "seeded",
            now,
            now,
        ),
        (
            "Customer Onboarding Checklist",
            (
                "<h1>Team Onboarding Checklist</h1>"
                "<p>Shared workspace guide maintained by <strong>Alex Rivera</strong>.</p>"
                "<ol>"
                "<li>Provision workspace accounts for new team members.</li>"
                "<li>Share starter templates and product briefs.</li>"
                "<li>Verify edit access and document persistence across sessions.</li>"
                "</ol>"
            ),
            alex_id,
            "seeded",
            now,
            now,
        ),
    ]
    conn.executemany(
        """
        INSERT INTO documents (title, content_html, owner_id, source_type, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        sample_docs,
    )

    docs = conn.execute("SELECT id, title FROM documents").fetchall()
    doc_map = {row["title"]: row["id"] for row in docs}

    conn.executemany(
        """
        INSERT INTO document_shares (document_id, user_id, permission, shared_by_id, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (doc_map["Q4 Product Launch Brief"], alex_id, "edit", usama_id, now),
            (doc_map["Customer Onboarding Checklist"], usama_id, "edit", alex_id, now),
        ],
    )
