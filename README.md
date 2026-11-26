# Ajaia Docs - Lightweight Collaborative Document Editor

A full-stack collaborative document editor built with **FastAPI**, **SQLite**, and **Quill.js**.

## Live Deployment & Test Accounts
- **Live URL:** <PASTE_RENDER_URL_HERE> *(Render free tier; cold start takes ~50s after 15 min idle)*
- **Walkthrough Video:** <PASTE_VIDEO_URL_HERE>
- **Seeded Demo Accounts (Top-Right Switcher):**
  - usama@ajaia.io - Usama Rasheed (Product Engineer)
  - alex@ajaia.io - Alex Rivera (Design Lead)
  - sara@ajaia.io - Sara Chen (Operations Lead)

## Core Features
1. **Rich-Text Editor:** Create, rename, edit, save (Save or Ctrl+S), delete, and reopen documents with Bold, Italic, Underline, Headings (H1-H3), and Bulleted/Numbered lists.
2. **File Upload:** Import .txt, .md, or .docx files (max 5 MB) into new editable documents. Unsupported formats return a 400 validation error.
3. **Sharing & Access Control:** Owner-controlled sharing by email/teammate dropdown, separating **My Documents** from **Shared With Me**. Only owners can rename, delete, or manage sharing.
4. **Persistence:** SQLite (data/ajaia_docs.db) storing users, documents, and document_shares.

## Local Setup & Run Instructions
`bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest -v
uvicorn app.main:app --host 127.0.0.1 --port 8000
`
Open http://127.0.0.1:8000 in your browser.
