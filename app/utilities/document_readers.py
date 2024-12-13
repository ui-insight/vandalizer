#!/usr/bin/env python3

from PyPDF2 import PdfReader
from pathlib import Path


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
        doc_path = Path("static/uploads") / doc_path

    if doc is None:
        if doc_path.endswith(".pdf"):
            return extract_text_from_pdf(doc_path)
        elif doc_path.endswith(".html"):
            return extract_text_from_html(doc_path)
    else:
        if doc.extension == "pdf" or doc.extension == "docx":
            return extract_text_from_pdf(doc_path)
        elif doc.extension == "html":
            return extract_text_from_html(doc_path)
