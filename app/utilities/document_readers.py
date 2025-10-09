#!/usr/bin/env python3

import os

from devtools import debug
from markitdown import MarkItDown
from PyPDF2 import PdfReader

from app.uillm.uipdf import UIPDF

OCR_ENDPOINT = os.environ.get("OCR_ENDPOINT", "https://ocr.insight.uidaho.edu/")

MIN_PDF_TEXT_LENGTH = 100
OUTPUT_FOLDER = os.path.join(os.path.dirname(__file__), "static/uploads")


def clean_markdown_nans(markdown_content: str) -> str:
    """Remove NaN values from markdown content."""
    # Replace NaN with empty cells
    cleaned = markdown_content.replace("| NaN |", "| |")
    cleaned = cleaned.replace("NaN", "")

    # Remove completely empty rows
    lines = cleaned.split("\n")
    filtered_lines = []
    for line in lines:
        if "|" in line:
            cells = [cell.strip() for cell in line.split("|")[1:-1]]
            # Keep if has content or is header separator
            if any(cell and cell != "---" for cell in cells) or all(
                cell in ["---", ""] for cell in cells
            ):
                filtered_lines.append(line)
        else:
            filtered_lines.append(line)

    return "\n".join(filtered_lines)


# Modify your existing function:
def convert_to_markdown(doc_path: str, keep_data_uris=True) -> str:
    """Convert a document to Markdown format."""
    md = MarkItDown(enable_plugins=False)
    result = md.convert(doc_path, keep_data_uris=keep_data_uris)

    # Clean up NaN values
    cleaned_content = clean_markdown_nans(result.text_content)

    return cleaned_content


def ocr_extract_text_from_pdf(pdf_path: str, retries=3) -> str:
    """Extract text from a PDF file using PyMuPDF and OCR.
    If the native text extraction is insufficient, OCR is applied.
    """
    debug("Extracting text with ocr for ", pdf_path)
    for _i in range(retries):
        try:
            return UIPDF.convert_to_text_demo(pdf_path)
        except Exception as e:
            debug(f"Error extracting text from PDF: {e}")
            return ""
        return ""
    return ""


def extract_text_from_pdf(pdf_path):
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text()
    return text


def extract_text_from_html(html_path):
    with open(html_path, encoding="utf-8") as file:
        return file.read()


def extract_text_from_doc(doc_path, doc=None):
    if doc and doc.raw_text and len(doc.raw_text) > 0:
        return doc.raw_text

    doc_path_str = str(doc_path)

    if doc is None:
        if doc_path_str.endswith(".pdf"):
            return ocr_extract_text_from_pdf(doc_path_str)
        elif doc_path_str.endswith(".html"):
            return convert_to_markdown(doc_path_str, keep_data_uris=False)
        elif doc_path_str.endswith((".txt", ".md", ".csv")):
            with open(doc_path_str, encoding="utf-8") as file:
                return file.read()

        return None
    else:
        debug(doc)
        debug(doc.raw_text)
        debug(doc_path_str)
        debug(doc.extension)
        if doc.extension in {"pdf"}:
            return ocr_extract_text_from_pdf(doc_path_str)
        elif doc.extension in {"docx", "doc"}:
            return extract_text_from_pdf(doc_path_str)
        elif doc.extension == "html":
            return extract_text_from_html(doc_path_str)
        elif doc.extension in {"txt", "md", "csv"}:
            with open(doc_path_str, encoding="utf-8") as file:
                return file.read()
    return None

def extract_text_from_file(file_path: str, file_extension: str) -> str:
    """Extract text from a file based on its extension."""
    file_extension = file_extension.lower().lstrip('.')
    
    try:
        # PDF files
        if file_extension == "pdf":
            # Try basic extraction first
            text = extract_text_from_pdf(file_path)
            
            # If text is too short, try OCR
            MIN_PDF_TEXT_LENGTH = 100
            if len(text.strip()) < MIN_PDF_TEXT_LENGTH:
                debug(f"PDF text too short ({len(text)} chars), trying OCR...")
                text = ocr_extract_text_from_pdf(file_path)
            
            return text
        
        # HTML files
        elif file_extension in ["html", "htm"]:
            return convert_to_markdown(file_path, keep_data_uris=False)
        
        # Plain text files
        elif file_extension in ["txt", "md", "csv", "json", "xml", "log"]:
            with open(file_path, encoding="utf-8") as file:
                return file.read()
        
        # Office documents (DOCX, DOC, XLSX, PPTX, etc.)
        elif file_extension in ["docx", "doc", "xlsx", "xls", "pptx", "ppt"]:
            return convert_to_markdown(file_path, keep_data_uris=False)
        
        # Code files
        elif file_extension in ["py", "js", "java", "cpp", "c", "h", "css", "sql"]:
            with open(file_path, encoding="utf-8") as file:
                return file.read()
        
        # Fallback: try markdown conversion
        else:
            try:
                return convert_to_markdown(file_path, keep_data_uris=False)
            except Exception as e:
                debug(f"MarkItDown conversion failed: {e}")
                # Last resort: try reading as plain text
                try:
                    with open(file_path, encoding="utf-8") as file:
                        return file.read()
                except:
                    with open(file_path, encoding="latin-1") as file:
                        return file.read()
    
    except Exception as e:
        print(f"Error extracting text from {file_path}: {e}")
        return f"[Error extracting content: {str(e)}]"
