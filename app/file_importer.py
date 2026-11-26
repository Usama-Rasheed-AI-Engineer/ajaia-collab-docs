import html
from io import BytesIO
from pathlib import Path
import bleach
from docx import Document as DocxDocument
import markdown

ALLOWED_EXTENSIONS = {".txt", ".md", ".docx"}
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB

ALLOWED_TAGS = [
    "p",
    "br",
    "strong",
    "b",
    "em",
    "i",
    "u",
    "s",
    "h1",
    "h2",
    "h3",
    "ul",
    "ol",
    "li",
    "blockquote",
    "pre",
    "code",
]


def sanitize_html(raw_html: str) -> str:
    cleaned = bleach.clean(raw_html or "", tags=ALLOWED_TAGS, attributes={}, strip=True)
    return cleaned.strip()


def _parse_txt(raw_bytes: bytes) -> str:
    text = raw_bytes.decode("utf-8", errors="replace").strip()
    if not text:
        return "<p></p>"
    paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
    return "".join(f"<p>{html.escape(p)}</p>" for p in paragraphs)


def _parse_md(raw_bytes: bytes) -> str:
    text = raw_bytes.decode("utf-8", errors="replace").strip()
    if not text:
        return "<p></p>"
    rendered = markdown.markdown(text, extensions=["extra", "nl2br"])
    return sanitize_html(rendered)


def _format_docx_runs(paragraph) -> str:
    parts: list[str] = []
    for run in paragraph.runs:
        text = html.escape(run.text or "")
        if not text:
            continue
        if run.bold:
            text = f"<strong>{text}</strong>"
        if run.italic:
            text = f"<em>{text}</em>"
        if run.underline:
            text = f"<u>{text}</u>"
        parts.append(text)
    return "".join(parts) if parts else html.escape(paragraph.text or "")


def _parse_docx(raw_bytes: bytes) -> str:
    doc = DocxDocument(BytesIO(raw_bytes))
    blocks: list[str] = []
    list_buffer: list[str] = []
    list_tag: str | None = None

    def flush_list() -> None:
        nonlocal list_buffer, list_tag
        if list_buffer and list_tag:
            items = "".join(f"<li>{item}</li>" for item in list_buffer)
            blocks.append(f"<{list_tag}>{items}</{list_tag}>")
        list_buffer = []
        list_tag = None

    for para in doc.paragraphs:
        raw_text = (para.text or "").strip()
        if not raw_text:
            flush_list()
            continue

        style_name = (para.style.name if para.style else "").lower()
        inline_html = _format_docx_runs(para)

        if "list bullet" in style_name:
            if list_tag != "ul":
                flush_list()
                list_tag = "ul"
            list_buffer.append(inline_html)
            continue

        if "list number" in style_name:
            if list_tag != "ol":
                flush_list()
                list_tag = "ol"
            list_buffer.append(inline_html)
            continue

        flush_list()
        if style_name.startswith("heading 1"):
            blocks.append(f"<h1>{inline_html}</h1>")
        elif style_name.startswith("heading 2"):
            blocks.append(f"<h2>{inline_html}</h2>")
        elif style_name.startswith("heading 3"):
            blocks.append(f"<h3>{inline_html}</h3>")
        else:
            blocks.append(f"<p>{inline_html}</p>")

    flush_list()
    if not blocks:
        return "<p></p>"
    return sanitize_html("".join(blocks))


def parse_uploaded_file(filename: str, raw_bytes: bytes) -> tuple[str, str, str]:
    safe_name = Path(filename or "").name.strip()
    if not safe_name:
        raise ValueError("A valid filename is required.")

    ext = Path(safe_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{ext or 'unknown'}'. Supported formats: .txt, .md, .docx."
        )

    if len(raw_bytes) == 0:
        raise ValueError("The uploaded file is empty.")

    if len(raw_bytes) > MAX_FILE_SIZE_BYTES:
        raise ValueError("File size exceeds the 5 MB limit.")

    title = Path(safe_name).stem.replace("_", " ").replace("-", " ").strip() or "Imported Document"

    if ext == ".txt":
        content_html = _parse_txt(raw_bytes)
    elif ext == ".md":
        content_html = _parse_md(raw_bytes)
    else:
        try:
            content_html = _parse_docx(raw_bytes)
        except Exception as exc:
            raise ValueError("Could not read .docx file. Please upload a valid Word document.") from exc

    return title[:120], content_html, ext.lstrip(".")
