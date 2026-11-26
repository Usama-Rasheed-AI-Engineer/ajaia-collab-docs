# AI-Native Workflow Note

## 1. AI Tools Used
- **Conversational AI Collaborator (Gemini):** Used for scope decomposition, SQLite schema design, FastAPI API scaffolding, pytest test case generation, and Docker configuration.

## 2. Where AI Materially Sped Up Work
- **Multi-Format File Ingestion (app/file_importer.py):** Rapidly built structured parsers for .docx paragraphs, inline runs (bold, italic, underline), headings, and bulleted/numbered lists using python-docx, alongside Markdown conversion.
- **Frontend Rich-Text Workspace (app/index.html):** Generated a zero-build-step UI integrating Quill.js with live state updates for owned vs. shared document lists and collaborator chips.
- **Automated Integration Tests (tests/test_app.py):** Accelerated writing isolated TestClient fixtures with temporary SQLite databases covering CRUD, XSS sanitization, .md/.docx uploads, and 403 access rules.

## 3. What AI-Generated Output Was Changed or Rejected
- **Rejected Heavy Frontend Build Tooling:** Avoided a separate React/Vite + Node split that would add dual build pipelines and CORS overhead; consolidated into a single FastAPI container serving static HTML + Quill.js.
- **Tightened HTML Sanitization & Owner Guards:** Replaced raw HTML trust with server-side bleach.clean tag allowlisting (ALLOWED_TAGS) to strip script tags, and enforced owner-only checks on document renaming and deletion (403 Forbidden for shared collaborators).
- **Fixed Terminal Paste Truncation & Test Path Resolution:** Caught a dropped parameter in revoke_share during terminal creation and added pytest.ini (pythonpath = .) so tests resolve cleanly on Windows.

## 4. Verification of Correctness, UX Quality & Reliability
- **Automated Test Suite:** Verified with pytest -v (4 passed) covering health/seeding, rich-text formatting round-trips, XSS stripping, .md/.docx parsing, invalid file rejection (.exe -> 400), and owner vs. collaborator 403 boundaries.
- **End-to-End Browser Verification:** Tested creating, formatting, saving, refreshing, importing files, sharing with sara@ajaia.io / alex@ajaia.io, switching active users, and revoking access.
