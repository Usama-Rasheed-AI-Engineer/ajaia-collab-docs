from io import BytesIO
from docx import Document as DocxDocument
from fastapi.testclient import TestClient
import pytest

from app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test_ajaia.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_file))
    with TestClient(app) as test_client:
        yield test_client


def test_health_and_seeded_workspace(client):
    health_res = client.get("/health")
    assert health_res.status_code == 200
    assert health_res.json()["status"] == "healthy"

    users_res = client.get("/api/users")
    emails = [u["email"] for u in users_res.json()["users"]]
    assert {"usama@ajaia.io", "alex@ajaia.io", "sara@ajaia.io"}.issubset(set(emails))

    docs_res = client.get("/api/documents", headers={"X-User-Email": "usama@ajaia.io"})
    assert docs_res.status_code == 200
    body = docs_res.json()
    assert len(body["owned"]) >= 2
    assert len(body["shared"]) >= 1


def test_create_edit_rename_and_persist_formatting(client):
    headers = {"X-User-Email": "usama@ajaia.io"}
    create_res = client.post(
        "/api/documents",
        headers=headers,
        json={"title": "Sprint Plan", "content_html": "<p>Initial draft</p>"},
    )
    assert create_res.status_code == 201
    doc_id = create_res.json()["id"]

    rich_html = (
        "<h1>Sprint Goals</h1>"
        "<p><strong>Bold</strong>, <em>Italic</em>, and <u>Underline</u>.</p>"
        "<ul><li>Bullet item</li></ul>"
        "<ol><li>Numbered item</li></ol>"
        "<script>alert('xss')</script>"
    )
    update_res = client.put(
        f"/api/documents/{doc_id}",
        headers=headers,
        json={"title": "Q4 Sprint Plan", "content_html": rich_html},
    )
    assert update_res.status_code == 200

    reopen_res = client.get(f"/api/documents/{doc_id}", headers=headers)
    assert reopen_res.status_code == 200
    reopened = reopen_res.json()
    assert reopened["title"] == "Q4 Sprint Plan"
    assert "<h1>Sprint Goals</h1>" in reopened["content_html"]
    assert "<strong>Bold</strong>" in reopened["content_html"]
    assert "<em>Italic</em>" in reopened["content_html"]
    assert "<u>Underline</u>" in reopened["content_html"]
    assert "<ul><li>Bullet item</li></ul>" in reopened["content_html"]
    assert "<ol><li>Numbered item</li></ol>" in reopened["content_html"]
    assert "<script>" not in reopened["content_html"]


def test_file_uploads_and_validation(client):
    headers = {"X-User-Email": "usama@ajaia.io"}

    # 1. Markdown upload
    md_res = client.post(
        "/api/documents/upload",
        headers=headers,
        files={"file": ("release_notes.md", b"# Release v1\n\n- **Fast** editor", "text/markdown")},
    )
    assert md_res.status_code == 201
    assert md_res.json()["title"] == "release notes"
    assert "<h1>Release v1</h1>" in md_res.json()["content_html"]
    assert "<strong>Fast</strong>" in md_res.json()["content_html"]

    # 2. DOCX upload
    docx_obj = DocxDocument()
    docx_obj.add_heading("Product Spec", level=1)
    p = docx_obj.add_paragraph()
    run = p.add_run("Core requirement")
    run.bold = True
    buf = BytesIO()
    docx_obj.save(buf)
    buf.seek(0)

    docx_res = client.post(
        "/api/documents/upload",
        headers=headers,
        files={
            "file": (
                "product_spec.docx",
                buf.getvalue(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert docx_res.status_code == 201
    assert "<h1>Product Spec</h1>" in docx_res.json()["content_html"]
    assert "<strong>Core requirement</strong>" in docx_res.json()["content_html"]

    # 3. Unsupported file type rejected cleanly
    bad_res = client.post(
        "/api/documents/upload",
        headers=headers,
        files={"file": ("malware.exe", b"MZ123", "application/octet-stream")},
    )
    assert bad_res.status_code == 400
    assert "Unsupported file type" in bad_res.json()["detail"]


def test_sharing_permissions_and_access_control(client):
    owner_headers = {"X-User-Email": "usama@ajaia.io"}
    sara_headers = {"X-User-Email": "sara@ajaia.io"}
    alex_headers = {"X-User-Email": "alex@ajaia.io"}

    created = client.post(
        "/api/documents",
        headers=owner_headers,
        json={"title": "Design Review", "content_html": "<p>V1</p>"},
    ).json()
    doc_id = created["id"]

    # Unshared user cannot read
    forbidden_res = client.get(f"/api/documents/{doc_id}", headers=sara_headers)
    assert forbidden_res.status_code == 403

    # Owner shares with Sara
    share_res = client.post(
        f"/api/documents/{doc_id}/share",
        headers=owner_headers,
        json={"email": "sara@ajaia.io", "permission": "edit"},
    )
    assert share_res.status_code == 200

    # Sara sees it in "shared", not "owned"
    sara_list = client.get("/api/documents", headers=sara_headers).json()
    assert any(d["id"] == doc_id for d in sara_list["shared"])
    assert not any(d["id"] == doc_id for d in sara_list["owned"])

    # Sara can edit content, but cannot rename or delete
    edit_res = client.put(
        f"/api/documents/{doc_id}",
        headers=sara_headers,
        json={"content_html": "<p>V2 updated by Sara</p>"},
    )
    assert edit_res.status_code == 200
    assert "V2 updated by Sara" in edit_res.json()["content_html"]

    rename_res = client.put(
        f"/api/documents/{doc_id}",
        headers=sara_headers,
        json={"title": "Hijacked Title"},
    )
    assert rename_res.status_code == 403

    delete_res = client.delete(f"/api/documents/{doc_id}", headers=sara_headers)
    assert delete_res.status_code == 403

    # Owner revokes Sara's access
    sara_id = [u["id"] for u in client.get("/api/users").json()["users"] if u["email"] == "sara@ajaia.io"][0]
    revoke_res = client.delete(f"/api/documents/{doc_id}/share/{sara_id}", headers=owner_headers)
    assert revoke_res.status_code == 200
    assert client.get(f"/api/documents/{doc_id}", headers=sara_headers).status_code == 403
    assert client.get(f"/api/documents/{doc_id}", headers=alex_headers).status_code == 403
