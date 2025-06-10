#!/usr/bin/env python3

import os

from devtools import debug
from PyPDF2 import PdfReader

from app.uillm.uipdf import UIPDF

OCR_ENDPOINT = os.environ.get("OCR_ENDPOINT", "https://ocr.insight.uidaho.edu/")

MIN_PDF_TEXT_LENGTH = 100
# doctr_url = "https://ocr.insight.uidaho.edu/doctr"
OUTPUT_FOLDER = os.path.join(os.path.dirname(__file__), "static/uploads")


def ocr_extract_text_from_pdf(pdf_path: str, retries=3) -> str:
    """Extract text from a PDF file using PyMuPDF and OCR.
    If the native text extraction is insufficient, OCR is applied.
    """
    debug("Extracting text with ocr for ", pdf_path)
    extracted_text = ""
    for _i in range(retries):
        try:
            return UIPDF.convert_to_text(pdf_path)
        except Exception as e:
            debug(f"Error extracting text from PDF: {e}")
            return ""
        return ""
    return None


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
    debug(doc)
    debug(doc.raw_text)
    debug(doc_path_str)

    if doc is None:
        if doc_path_str.endswith(".pdf"):
            return ocr_extract_text_from_pdf(doc_path_str)
        elif doc_path_str.endswith(".html"):
            return extract_text_from_html(doc_path_str)
        elif doc_path_str.endswith((".txt", ".md", ".csv")):
            with open(doc_path_str, encoding="utf-8") as file:
                return file.read()

        return None
    else:
        debug(doc.extension)
        if doc.extension in {"pdf"}:
            # return extract_text_from_pdf(doc_path_str)
            return ocr_extract_text_from_pdf(doc_path_str)
        elif doc.extension in {"docx", "doc"}:
            return extract_text_from_pdf(doc_path_str)
        elif doc.extension == "html":
            return extract_text_from_html(doc_path_str)
        elif doc.extension in {"txt", "md", "csv"}:
            with open(doc_path_str, encoding="utf-8") as file:
                return file.read()
    return None
