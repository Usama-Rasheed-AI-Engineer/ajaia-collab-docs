# Architecture & Prioritization Note

## 1. System Overview
- **Frontend (pp/index.html + Quill.js 1.3.7):** Single-page collaborative workspace with a sidebar separating **My Documents** from **Shared With Me**, file import dropzone, rich-text toolbar, inline title editing, and collaborator management.
- **Backend (pp/main.py + FastAPI):** REST API managing document CRUD, multipart file uploads, active user resolution (X-User-Email), and server-side access enforcement.
- **File Parser & Sanitizer (pp/file_importer.py):** Converts .txt, .md (markdown), and .docx (python-docx) into semantic HTML and sanitizes output via leach against an explicit tag allowlist.
- **Persistence (pp/database.py + SQLite):** Relational schema (users, documents, document_shares) with foreign keys, UNIQUE(document_id, user_id) constraints, and idempotent startup seeding.

## 2. What Was Prioritized & Why
1. **Rich-Text Persistence Fidelity:** Stored sanitized semantic HTML so headings (H1-H3), bold, italic, underline, and lists survive refreshes and cross-user edits cleanly.
2. **Multi-Format Document Ingestion:** Supported .docx alongside .md and .txt to match real team document workflows, with strict extension and 5 MB size validation.
3. **Server-Side Access Control:** Enforced owner vs. collaborator permissions on every API route (403 Forbidden when non-owners attempt to rename, delete, or modify sharing).
4. **Zero-Friction Evaluation:** Seeded 3 demo accounts (usama@ajaia.io, lex@ajaia.io, sara@ajaia.io) and starter documents so reviewers can verify sharing flows immediately.

## 3. Intentional Scope Cuts
- **Real-Time WebSocket / CRDT Co-Editing:** Cut in favor of explicit save/reopen persistence (Save + Ctrl+S) to guarantee reliability within the 4-6 hour timebox.
- **OAuth / Password Auth:** Replaced with a deterministic seeded user switcher (X-User-Email) so sharing flows can be tested in one click.
- **External Object Storage:** Imported files convert directly into editable rich-text documents in SQLite, keeping deployment self-contained and free.

## 4. Next Steps (With Another 2-4 Hours)
1. Debounced autosave with optimistic concurrency checks (updated_at conflict warning).
2. Granular sharing roles (iewer read-only vs. editor).
3. Symmetric export to .md and .docx.
