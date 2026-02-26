"""Multi-format text extraction (PDF, DOCX, XLSX, HTML, etc.).

Ported from Flask app/utilities/document_readers.py.
All functions are synchronous — safe for Celery workers.
"""

import logging
import os
import re

from markitdown import MarkItDown
from PyPDF2 import PdfReader

logger = logging.getLogger(__name__)

MIN_PDF_TEXT_LENGTH = 100


def clean_markdown_nans(markdown_content: str) -> str:
    """Remove NaN values from markdown content."""
    cleaned = markdown_content.replace("| NaN |", "| |")
    cleaned = cleaned.replace("NaN", "")

    lines = cleaned.split("\n")
    filtered_lines = []
    for line in lines:
        if "|" in line:
            cells = [cell.strip() for cell in line.split("|")[1:-1]]
            if any(cell and cell != "---" for cell in cells) or all(
                cell in ["---", ""] for cell in cells
            ):
                filtered_lines.append(line)
        else:
            filtered_lines.append(line)

    return "\n".join(filtered_lines)


def convert_to_markdown(doc_path: str, keep_data_uris: bool = True) -> str:
    """Convert a document to Markdown format using MarkItDown."""
    md = MarkItDown(enable_plugins=False)
    result = md.convert(doc_path, keep_data_uris=keep_data_uris)
    return clean_markdown_nans(result.text_content)


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from a PDF using PyPDF2."""
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text()
    return text


def ocr_extract_text_from_pdf(pdf_path: str, retries: int = 3) -> str:
    """Extract text from a PDF using the UIPDF OCR endpoint.

    Falls back gracefully if the OCR service is unavailable.
    """
    ocr_endpoint = os.environ.get("OCR_ENDPOINT", "https://ocr.insight.uidaho.edu/")
    logger.info("Extracting text with OCR for %s", pdf_path)

    for _attempt in range(retries):
        try:
            import httpx

            with httpx.Client(timeout=120.0) as client:
                with open(pdf_path, "rb") as f:
                    resp = client.post(
                        ocr_endpoint.rstrip("/") + "/convert",
                        files={"file": (os.path.basename(pdf_path), f, "application/pdf")},
                    )
                if resp.status_code == 200:
                    return resp.text
        except Exception as e:
            logger.warning("OCR attempt failed: %s", e)

    return ""


def remove_images_from_markdown(markdown_text: str) -> str:
    """Remove all image references and their size attributes from markdown text."""
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", "", markdown_text)
    text = re.sub(r"!\[([^\]]*)\]\[[^\]]*\]", "", text)
    text = re.sub(r'\{[^}]*(?:width|height)\s*=\s*"[^"]*"[^}]*\}', "", text)
    text = re.sub(r'\{[^{}]*="[^"]*"[^{}]*\}', "", text)
    text = re.sub(r"^\s*\[[^\]]+\]:\s*[^\s]+.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n\s*\n\s*\n", "\n\n", text)
    text = re.sub(r"^\s+$", "", text, flags=re.MULTILINE)
    return text.strip()


def extract_text_from_file(file_path: str, file_extension: str) -> str:
    """Extract text from a file based on its extension.

    This is the primary entry point used by document_tasks.
    """
    file_extension = file_extension.lower().lstrip(".")

    try:
        if file_extension == "pdf":
            text = extract_text_from_pdf(file_path)
            if len(text.strip()) < MIN_PDF_TEXT_LENGTH:
                logger.info("PDF text too short (%d chars), trying OCR...", len(text))
                text = ocr_extract_text_from_pdf(file_path)
            return text

        elif file_extension in ("html", "htm"):
            return convert_to_markdown(file_path, keep_data_uris=False)

        elif file_extension in ("txt", "md", "csv", "json", "xml", "log"):
            with open(file_path, encoding="utf-8") as f:
                return f.read()

        elif file_extension in ("docx", "doc", "xlsx", "xls", "pptx", "ppt"):
            return convert_to_markdown(file_path, keep_data_uris=False)

        elif file_extension in ("py", "js", "java", "cpp", "c", "h", "css", "sql"):
            with open(file_path, encoding="utf-8") as f:
                return f.read()

        else:
            try:
                return convert_to_markdown(file_path, keep_data_uris=False)
            except Exception:
                try:
                    with open(file_path, encoding="utf-8") as f:
                        return f.read()
                except Exception:
                    with open(file_path, encoding="latin-1") as f:
                        return f.read()

    except Exception as e:
        logger.error("Error extracting text from %s: %s", file_path, e)
        return f"[Error extracting content: {e!s}]"
