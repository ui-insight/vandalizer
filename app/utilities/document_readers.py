#!/usr/bin/env python3

from PyPDF2 import PdfReader
from pathlib import Path
from flask import current_app
import httpx
import pymupdf


MIN_PDF_TEXT_LENGTH = 100
doctr_url = "https://ocr.insight.uidaho.edu/doctr"

def ocr_extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract text from a PDF file using PyMuPDF and OCR.
    If the native text extraction is insufficient, OCR is applied.
    """
    doc = pymupdf.open(pdf_path)
    all_text = ""
    for page in doc:
        all_text += page.get_text()
    if len(all_text) < MIN_PDF_TEXT_LENGTH:
        files = {"file": Path(pdf_path).read_bytes()}
        response = httpx.post(doctr_url, files=files, timeout=300)
        all_text = response.content.decode("utf-8")
    return all_text

def extract_text_from_pdf(pdf_path):
    # path has to contain static/uploads/ the file name
    if "static/uploads/" not in pdf_path:
        pdf_path = Path("static/uploads") / pdf_path

    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text()
    return text


def extract_text_from_html(html_path):

    if "static/uploads/" not in html_path:
        html_path = Path("static/uploads") / html_path

    with open(html_path, "r", encoding="utf-8") as file:
        return file.read()


def extract_text_from_doc(doc_path, doc=None):
    if "static/uploads/" not in doc_path:
        doc_path = Path(current_app.root_path) / "static/uploads" / doc_path

    doc_path_str = str(doc_path)

    if doc is None:
        if doc_path_str.endswith(".pdf"):
            return extract_text_from_pdf(doc_path_str)
        elif doc_path_str.endswith(".html"):
            return extract_text_from_html(doc_path_str)
    else:
        if doc.extension == "pdf" or doc.extension == "docx":
            return extract_text_from_pdf(doc_path_str)
        elif doc.extension == "html":
            return extract_text_from_html(doc_path_str)
