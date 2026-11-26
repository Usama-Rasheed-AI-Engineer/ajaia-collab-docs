from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.database import get_connection, init_db, utc_now
from app.file_importer import parse_uploaded_file, sanitize_html

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_USER_EMAIL = "usama@ajaia.io"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Ajaia Docs - Collaborative Document Editor", version="1.0.0", lifespan=lifespan)


class DocumentCreate(BaseModel):
    title: str = Field(default="Untitled Document", max_length=120)
    content_html: str = Field(default="<p></p>")


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    content_html: str | None = Field(default=None)


class ShareRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=160)
    permission: str = Field(default="edit")


def resolve_current_user(conn, x_user_email: str | None) -> dict[str, Any]:
    email = (x_user_email or DEFAULT_USER_EMAIL).strip().lower()
    row = conn.execute(
        "SELECT id, name, email, role_label FROM users WHERE LOWER(email) = ?",
        (email,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail=f"Unknown user account: {email}")
    return dict(row)


def get_document_with_access(conn, doc_id: int, user_id: int) -> tuple[dict[str, Any], str]:
    doc_row = conn.execute(
        """
        SELECT d.id, d.title, d.content_html, d.owner_id, d.source_type,
               d.created_at, d.updated_at,
               u.name AS owner_name, u.email AS owner_email
        FROM documents d
        JOIN users u ON u.id = d.owner_id
        WHERE d.id = ?
        """,
        (doc_id,),
    ).fetchone()
    if not doc_row:
        raise HTTPException(status_code=404, detail="Document not found.")

    doc = dict(doc_row)
    if doc["owner_id"] == user_id:
        return doc, "owner"

    share_row = conn.execute(
        "SELECT permission FROM document_shares WHERE document_id = ? AND user_id = ?",
        (doc_id, user_id),
    ).fetchone()
    if not share_row:
        raise HTTPException(status_code=403, detail="You do not have access to this document.")

    return doc, "shared"


def get_share_list(conn, doc_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT ds.user_id, u.name, u.email, u.role_label, ds.permission, ds.created_at
        FROM document_shares ds
        JOIN users u ON u.id = ds.user_id
        WHERE ds.document_id = ?
        ORDER BY ds.created_at ASC
        """,
        (doc_id,),
    ).fetchall()
    return [dict(r) for r in rows]


@app.get("/health")
def health() -> dict[str, str]:
    init_db()
    with get_connection() as conn:
        doc_count = conn.execute("SELECT COUNT(*) AS cnt FROM documents").fetchone()["cnt"]
    return {"status": "healthy", "database": "sqlite", "documents": str(doc_count)}


@app.get("/api/users")
def list_users() -> dict[str, list[dict[str, Any]]]:
    init_db()
    with get_connection() as conn:
        rows = conn.execute("SELECT id, name, email, role_label FROM users ORDER BY id ASC").fetchall()
    return {"users": [dict(r) for r in rows]}


@app.get("/api/documents")
def list_documents(x_user_email: str | None = Header(default=None)) -> dict[str, Any]:
    init_db()
    with get_connection() as conn:
        user = resolve_current_user(conn, x_user_email)

        owned_rows = conn.execute(
            """
            SELECT d.id, d.title, d.owner_id, d.source_type, d.created_at, d.updated_at,
                   u.name AS owner_name, u.email AS owner_email,
                   (SELECT COUNT(*) FROM document_shares ds WHERE ds.document_id = d.id) AS shared_count
            FROM documents d
            JOIN users u ON u.id = d.owner_id
            WHERE d.owner_id = ?
            ORDER BY d.updated_at DESC
            """,
            (user["id"],),
        ).fetchall()

        shared_rows = conn.execute(
            """
            SELECT d.id, d.title, d.owner_id, d.source_type, d.created_at, d.updated_at,
                   u.name AS owner_name, u.email AS owner_email,
                   ds.permission
            FROM document_shares ds
            JOIN documents d ON d.id = ds.document_id
            JOIN users u ON u.id = d.owner_id
            WHERE ds.user_id = ?
            ORDER BY d.updated_at DESC
            """,
            (user["id"],),
        ).fetchall()

    return {
        "current_user": user,
        "owned": [dict(r) for r in owned_rows],
        "shared": [dict(r) for r in shared_rows],
    }


@app.post("/api/documents", status_code=201)
def create_document(
    payload: DocumentCreate,
    x_user_email: str | None = Header(default=None),
) -> dict[str, Any]:
    init_db()
    title = payload.title.strip() or "Untitled Document"
    clean_html = sanitize_html(payload.content_html) or "<p></p>"
    now = utc_now()

    with get_connection() as conn:
        user = resolve_current_user(conn, x_user_email)
        cursor = conn.execute(
            """
            INSERT INTO documents (title, content_html, owner_id, source_type, created_at, updated_at)
            VALUES (?, ?, ?, 'blank', ?, ?)
            """,
            (title, clean_html, user["id"], now, now),
        )
        doc_id = cursor.lastrowid
        doc, access_role = get_document_with_access(conn, doc_id, user["id"])
        doc["access_role"] = access_role
        doc["shared_with"] = []
    return doc


@app.post("/api/documents/upload", status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    x_user_email: str | None = Header(default=None),
) -> dict[str, Any]:
    init_db()
    raw_bytes = await file.read()
    try:
        title, content_html, source_type = parse_uploaded_file(file.filename or "", raw_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    now = utc_now()
    with get_connection() as conn:
        user = resolve_current_user(conn, x_user_email)
        cursor = conn.execute(
            """
            INSERT INTO documents (title, content_html, owner_id, source_type, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (title, content_html, user["id"], source_type, now, now),
        )
        doc_id = cursor.lastrowid
        doc, access_role = get_document_with_access(conn, doc_id, user["id"])
        doc["access_role"] = access_role
        doc["shared_with"] = []
    return doc


@app.get("/api/documents/{doc_id}")
def get_document(
    doc_id: int,
    x_user_email: str | None = Header(default=None),
) -> dict[str, Any]:
    init_db()
    with get_connection() as conn:
        user = resolve_current_user(conn, x_user_email)
        doc, access_role = get_document_with_access(conn, doc_id, user["id"])
        doc["access_role"] = access_role
        doc["shared_with"] = get_share_list(conn, doc_id)
    return doc


@app.put("/api/documents/{doc_id}")
def update_document(
    doc_id: int,
    payload: DocumentUpdate,
    x_user_email: str | None = Header(default=None),
) -> dict[str, Any]:
    init_db()
    with get_connection() as conn:
        user = resolve_current_user(conn, x_user_email)
        doc, access_role = get_document_with_access(conn, doc_id, user["id"])

        new_title = doc["title"]
        if payload.title is not None:
            cleaned_title = payload.title.strip()
            if not cleaned_title:
                raise HTTPException(status_code=400, detail="Document title cannot be empty.")
            if cleaned_title != doc["title"] and access_role != "owner":
                raise HTTPException(
                    status_code=403,
                    detail="Only the document owner can rename this document.",
                )
            new_title = cleaned_title

        new_content = (
            sanitize_html(payload.content_html)
            if payload.content_html is not None
            else doc["content_html"]
        )
        now = utc_now()

        conn.execute(
            """
            UPDATE documents
            SET title = ?, content_html = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_title, new_content, now, doc_id),
        )
        updated_doc, updated_role = get_document_with_access(conn, doc_id, user["id"])
        updated_doc["access_role"] = updated_role
        updated_doc["shared_with"] = get_share_list(conn, doc_id)
    return updated_doc


@app.delete("/api/documents/{doc_id}")
def delete_document(
    doc_id: int,
    x_user_email: str | None = Header(default=None),
) -> dict[str, str]:
    init_db()
    with get_connection() as conn:
        user = resolve_current_user(conn, x_user_email)
        _, access_role = get_document_with_access(conn, doc_id, user["id"])
        if access_role != "owner":
            raise HTTPException(status_code=403, detail="Only the document owner can delete this document.")
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    return {"status": "deleted"}


@app.post("/api/documents/{doc_id}/share")
def share_document(
    doc_id: int,
    payload: ShareRequest,
    x_user_email: str | None = Header(default=None),
) -> dict[str, Any]:
    init_db()
    target_email = payload.email.strip().lower()
    if payload.permission not in {"edit"}:
        raise HTTPException(status_code=400, detail="Supported sharing permission is 'edit'.")

    with get_connection() as conn:
        user = resolve_current_user(conn, x_user_email)
        doc, access_role = get_document_with_access(conn, doc_id, user["id"])
        if access_role != "owner":
            raise HTTPException(status_code=403, detail="Only the document owner can share this document.")

        target_row = conn.execute(
            "SELECT id, name, email FROM users WHERE LOWER(email) = ?",
            (target_email,),
        ).fetchone()
        if not target_row:
            raise HTTPException(
                status_code=404,
                detail=f"User '{target_email}' not found. Available accounts: usama@ajaia.io, alex@ajaia.io, sara@ajaia.io.",
            )

        if target_row["id"] == doc["owner_id"]:
            raise HTTPException(status_code=400, detail="You already own this document.")

        now = utc_now()
        conn.execute(
            """
            INSERT INTO document_shares (document_id, user_id, permission, shared_by_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(document_id, user_id)
            DO UPDATE SET permission = excluded.permission, shared_by_id = excluded.shared_by_id
            """,
            (doc_id, target_row["id"], payload.permission, user["id"], now),
        )
        shared_with = get_share_list(conn, doc_id)

    return {"status": "shared", "shared_with": shared_with}


@app.delete("/api/documents/{doc_id}/share/{target_user_id}")
def revoke_share(
    doc_id: int,
    target_user_id: int,
    x_user_email: str | None = Header(default=None),
) -> dict[str, Any]:
    init_db()
    with get_connection() as conn:
        user = resolve_current_user(conn, x_user_email)
        _, access_role = get_document_with_access(conn, doc_id, user["id"])
        if access_role != "owner":
            raise HTTPException(status_code=403, detail="Only the document owner can manage sharing.")

        conn.execute(
            "DELETE FROM document_shares WHERE document_id = ? AND user_id = ?",
            (doc_id, target_user_id),
        )
        shared_with = get_share_list(conn, doc_id)

    return {"status": "revoked", "shared_with": shared_with}


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((ROOT_DIR / "app" / "index.html").read_text(encoding="utf-8"))
