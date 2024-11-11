#!/usr/bin/env python3

from PyPDF2 import PdfReader


def extract_text_from_pdf(pdf_path):
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text()
    return text


def extract_text_from_html(html_path):
    with open(html_path, "r", encoding="utf-8") as file:
        return file.read()


def extract_text_from_doc(doc_path, doc=None):
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
