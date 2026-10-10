"""
utils/file_extractor.py — Extracts plain text from an uploaded JD file
(PDF, DOCX, or TXT) so Agent 1 (JD Parser) can process it the same way
regardless of upload format.
"""

import io

import PyPDF2
import docx

ALLOWED_EXTENSIONS = (".pdf", ".docx", ".txt")


def extract_text_from_file(file) -> dict:
    """
    Args:
        file: a werkzeug FileStorage object (from request.files["file"]).

    Returns:
        {"success": True, "text": "..."} on success, or
        {"success": False, "message": "..."} on failure — this shape lets
        the route just check `if not extraction["success"]` without
        needing a try/except of its own.
    """
    filename = (file.filename or "").lower()

    if not filename.endswith(ALLOWED_EXTENSIONS):
        return {
            "success": False,
            "message": f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        }

    try:
        if filename.endswith(".pdf"):
            reader = PyPDF2.PdfReader(file)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)

        elif filename.endswith(".docx"):
            document = docx.Document(file)
            text = "\n".join(p.text for p in document.paragraphs)

        else:  # .txt
            text = file.read().decode("utf-8", errors="ignore")

        text = text.strip()
        if not text:
            return {
                "success": False,
                "message": "No readable text found in the file (it may be a scanned/image-only document).",
            }

        return {"success": True, "text": text}

    except Exception as e:
        return {"success": False, "message": f"Failed to read file: {e}"}