#!/usr/bin/env python3

from PyPDF2 import PdfReader
from pathlib import Path
from flask import current_app
import httpx
import pymupdf
from devtools import debug
import os
import fitz
import requests
import subprocess
import pymupdf4llm
import fitz
from concurrent.futures import ThreadPoolExecutor, as_completed
from markdownify import markdownify as md
import re
import os
import requests
from dataclasses import dataclass

OCR_ENDPOINT = os.environ.get("OCR_ENDPOINT", "https://ocr.insight.uidaho.edu/")

MIN_PDF_TEXT_LENGTH = 100
# doctr_url = "https://ocr.insight.uidaho.edu/doctr"
OUTPUT_FOLDER = os.path.join(os.path.dirname(__file__), "static/uploads")


class APIResponse:
    def __init__(
        self,
        status=None,
        message=None,
        http_status=None,
        text=None,
        tables=None,
        images=None,
    ):
        self.status = status
        self.message = message
        self.http_status = http_status
        self.text = text
        self.tables = tables
        self.images = images

    def __repr__(self):
        return f"APIResponse(status={self.status}, message={self.message}, http_status={self.http_status}, text={self.text}, tables={self.tables}, images={self.images})"


def ocr_extract_text_from_pdf(pdf_path: str, retries=3) -> str:
    """
    Extract text from a PDF file using PyMuPDF and OCR.
    If the native text extraction is insufficient, OCR is applied.
    """
    debug("Extracting text with ocr for ", pdf_path)
    extracted_text = ""
    for i in range(retries):
        try:
            processor = PDFProcessor(
                ocr_tool="doctr",
                format="markdown",
                garble_ratio=0.2,
                file_path=pdf_path,
                output_path=None,
            )
            output = processor.parse(extract_images=False, extract_tables=False)
            extracted_text = output.text
            if output.status != "error" and len(extracted_text) > 0:
                return output.text
        except Exception as e:
            debug(f"Error extracting text from PDF: {e}")
            return ""
        return ""


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
    if doc and doc.raw_text and len(doc.raw_text) > 0:
        return doc.raw_text

    doc_path_str = str(doc_path)
    debug(doc_path_str)

    if doc is None:
        if doc_path_str.endswith(".pdf"):
            return ocr_extract_text_from_pdf(doc_path_str)
        elif doc_path_str.endswith(".html"):
            return extract_text_from_html(doc_path_str)
    else:
        if doc.extension == "pdf" or doc.extension == "docx":
            # return extract_text_from_pdf(doc_path_str)
            return ocr_extract_text_from_pdf(doc_path_str)
        elif doc.extension == "html":
            return extract_text_from_html(doc_path_str)


class PDFProcessor:
    """Core PDF processing functionality that can be used both natively and as an API resource"""

    def __init__(self, format, garble_ratio, ocr_tool, file_path, output_path):
        """Initialize with configuration"""
        self.fallback = "ocr"
        self.format = format
        self.garble_ratio = garble_ratio
        self.ocr_tool = ocr_tool
        self.file_path = file_path
        self.output_path = output_path

    def check_pdf_quality(self):
        pdf_status = []
        image_status = []
        # Extract text from PDF
        try:
            pdf_document = fitz.open(self.file_path)

        except Exception as e:
            pdf_document = None
            message, status = (
                f"Error - there was a problem uploading your document: {str(e)}",
                500,
            )

        try:
            messages = []

            for page_number in range(min(3, pdf_document.page_count)):
                page = pdf_document.load_page(page_number)
                text = page.get_text("text")

                # Check if the text is present and not garbled
                if text.strip():
                    # Optionally, implement a function to check for garbled text
                    if is_text_garbled(text, self.garble_ratio):
                        messages += [f"Text is garbled on page #{page_number}"]
                        pdf_status.append(True)
                        break
                    else:
                        messages += [f"Text is clear on page #{page_number}"]
                        pdf_status.append(False)
                else:
                    messages += [f"No native text found on page #{page_number}"]
                    pdf_status.append(True)

                if page.get_images():
                    image_status.append(True)
                    messages += [f"An image was found on page #{page_number}"]
                    break
                else:
                    image_status.append(False)

            print("\n".join(messages))
            message, status = "document successfully checked", 200

        except Exception as e:
            message, status = f"Error - preliminary parsing failed ... \n {e}", 500

        return {
            "message": message,
            "http_status": status,
            "images": image_status,
            "text_quality": pdf_status,
        }, pdf_document

    # regular parsing. if document contains any images the whole document is sent to OCR
    def parse(self, extract_images=False, extract_tables=False):
        # initialize output object
        api_response = APIResponse()

        try:
            # check pdf quality
            quality_response, pdf_document = self.check_pdf_quality()
            images_found = quality_response["images"]
            pdf_quality = quality_response["text_quality"]

        except Exception as e:
            api_response.status = ("Error",)
            api_response.message = (quality_response["message"],)
            api_response.http_status = str(quality_response["http_status"])

            return api_response

        try:
            # if OCR not necessary proceed with basic text extraction
            if not any(images_found) and not any(pdf_quality) or self.fallback != "ocr":
                full_text, tables, images = parse_basic(
                    document=pdf_document,
                    upload_path=self.file_path,
                    format=self.format,
                    extract_tables=extract_tables,
                    extract_images=extract_images,
                )

                api_response.status = ("Success",)
                api_response.message = ("document successfully parsed by PyMuPDF",)
                api_response.http_status = "200"
                api_response.text = full_text
                api_response.tables = tables
                api_response.images = images

                pdf_document.close()  # Ensure the PDF document is closed on exception

                return api_response

            else:
                # if images or low quality send to OCR
                try:
                    with open(self.file_path, "rb") as f:
                        files = {"file": f}

                        ocr_response = requests.post(
                            OCR_ENDPOINT + self.ocr_tool, files=files, timeout=300
                        )

                    api_response.status = ("Success",)
                    api_response.message = ("document successfully parsed by OCR",)
                    api_response.http_status = "200"
                    api_response.text = ocr_response.text
                    api_response.tables = []
                    api_response.images = []
                    # response = ocrmypdf(upload_path = file_path, output_path = file_output_path, return_as = format_type)
                    pdf_document.close()

                    return api_response

                except Exception as e:
                    pdf_document.close()
                    api_response.status = "error"
                    api_response.message = f"Error - OCR tool @ {OCR_ENDPOINT + self.ocr_tool} failed with message: {e}"
                    api_response.http_status = "500"
                    return api_response

        except Exception as e:
            pdf_document.close()

            api_response.status = "error"
            api_response.message = f"Error - unable to parse document: \n {e}"
            api_response.http_status = "500"
            return api_response

    # faster option which applies OCR to necessary pages only and utilizes multithreading of page extraction
    def parse_document_fast(self, extract_images=False, extract_tables=False):
        api_response = APIResponse()

        try:
            pdf_document = fitz.open(self.file_path)

        except Exception as e:
            api_response.status = "error"
            api_response.message = (
                f"Error - there was a problem uploading your document: {str(e)}"
            )
            api_response.http_status = "500"

        try:
            full_text, tables, images = parse_fast(
                document=pdf_document,
                upload_path=self.file_path,
                gr=self.garble_ratio,
                format=self.format,
                endpoint=OCR_ENDPOINT + self.ocr_tool,
                out_path=self.output_path,
                extract_tables=extract_tables,
                extract_images=extract_images,
            )

            api_response.status = ("Success",)
            api_response.message = "document successfully parsed"
            api_response.http_status = "200"
            api_response.text = full_text
            api_response.tables = tables
            api_response.images = images

            pdf_document.close()  # Ensure the PDF document is closed on exception
            return api_response

        except Exception as e:
            pdf_document.close()

            api_response.status = "error"
            api_response.message = f"Error - unable to parse document: \n {e}"
            api_response.http_status = "500"
            return api_response

    def parse_document_fast_by_page(self, extract_images=False, extract_tables=False):
        api_response = APIResponse()

        try:
            pdf_document = fitz.open(self.file_path)

        except Exception as e:
            api_response.status = "error"
            api_response.message = (
                f"Error - there was a problem uploading your document: {str(e)}"
            )
            api_response.http_status = "500"

        try:
            page_text, tables, images = parse_fast_by_page(
                document=pdf_document,
                upload_path=self.file_path,
                gr=self.garble_ratio,
                format=self.format,
                endpoint=OCR_ENDPOINT + self.ocr_tool,
                out_path=self.output_path,
                extract_tables=extract_tables,
                extract_images=extract_images,
            )

            api_response.status = ("Success",)
            api_response.message = ("document successfully parsed",)
            api_response.http_status = "200"
            api_response.text = page_text
            api_response.tables = tables
            api_response.images = images

            pdf_document.close()  # Ensure the PDF document is closed on exception
            return api_response

        except Exception as e:
            pdf_document.close()

            api_response.status = "error"
            api_response.message = f"Error - unable to parse document: \n {e}"
            api_response.http_status = "500"
            return api_response


def is_text_garbled(text, threshold=0.2):
    """
    Check if the text is garbled by analyzing the proportion of non-alphanumeric characters.

    Parameters:
    - text (str): The text to analyze.
    - threshold (float): The proportion of non-alphanumeric characters above which text is considered garbled.

    Returns:
    - bool: True if text is considered garbled, False otherwise.
    """
    if not text:
        return True

    # Count the number of alphanumeric characters
    alphanumeric_count = sum(c.isalnum() for c in text)

    # Count the total number of characters
    total_count = len(text)

    # Calculate the proportion of alphanumeric characters
    if total_count == 0:
        return True  # Consider empty text as garbled

    alphanumeric_ratio = alphanumeric_count / total_count

    # If the proportion of alphanumeric characters is below the threshold, consider it garbled
    return alphanumeric_ratio < (1 - threshold)


def clean_markdown(text):
    text = re.sub(r"\\(\d+\.)", r"\1", text)
    text = re.sub(r"\\([\.#\-_])", r"\1", text)
    text = re.sub(r"\\([\$\+])", r"\1", text)
    return text


def parse_basic(
    document, upload_path, format, extract_tables=True, extract_images=True
):
    full_text = ""
    tables = {}
    images = {}
    if format == "plain text":
        for page_number in range(document.page_count):
            page = document.load_page(page_number)
            if extract_tables:
                if page.find_tables():
                    tables = tables | {f"page{page_number}": page.find_tables()}

            if extract_images:
                if page.get_images():
                    xrefs = [i[0] for i in page.get_images()]
                    imagebytes = {
                        {f"image{i}": fitz.Pixmap(document, ref).tobytes()}
                        for i, ref in enumerate(xrefs)
                    }
                    images = images | {f"page{page_number}": imagebytes}

            full_text += page.get_text("text")

        return full_text, tables, images
    else:
        full_text = pymupdf4llm.to_markdown(upload_path)
        return full_text, {}, {}


def save_page_to_pdf(doc, page_number, output_path):
    try:
        # Create a new PDF document
        new_doc = fitz.open()

        # Insert the page from the original document to the new document
        new_doc.insert_pdf(doc, from_page=page_number, to_page=page_number)

        # Define the path to save the new PDF
        page_path = os.path.join(output_path, f"page_{page_number}.pdf")

        # Save the new PDF document
        new_doc.save(page_path)
        new_doc.close()
    except Exception as e:
        print(f"ERROR: There was a problem saving page {page_number} to .pdf: {e}")
        new_doc.close()

    return page_path


def process_page(
    document,
    page_number: int,
    gr: float = 0.2,
    extract_tables: bool = False,
    extract_images: bool = False,
    endpoint: str = "https://ocr.insight.uidaho.edu/ocr",
    output_dir: str = "./",
    **kwargs,
):
    images = {}
    tables = {}
    # load page
    page = document.load_page(page_number)

    if page.get_text():
        bad_text = is_text_garbled(page.get_text("text", sort=True), gr)
        if bad_text:
            print(f"text on page {page_number} is garbled")
    else:
        bad_text = False

    if page.get_images():
        found_im = True
        print(f"An image was found on page {page_number}")
    else:
        found_im = False

    # determine if the page needs OCR
    if any([found_im, bad_text]):
        ocr_page = True

        # extract images if necessary
        if extract_images and found_im:
            try:
                xrefs = [i[0] for i in page.get_images()]
                imagebytes = {
                    {f"image{i}": fitz.Pixmap(document, ref).tobytes()}
                    for i, ref in enumerate(xrefs)
                }
                images = {f"page{page_number}": imagebytes}
            except Exception as e:
                print(f"ERROR: {e}")
                images = {}
        else:
            images = {}
    else:
        images = {}
        ocr_page = False

    # extract tables if necessary
    if extract_tables:
        try:
            tabs = page.find_tables()
            if tabs.tables:
                tables = {f"page{page_number}": [i.extract() for i in tabs]}
        except Exception as e:
            if not page.get_text() or "not a textpage" in str(e):
                print("Page is not a textpage")
            else:
                print(f"ERROR: {e}")
            tables = {}
    else:
        tables = {}

    # OCR the page if the ocr indicator is active
    if ocr_page == True:
        print(f"Using OCR tool @ {endpoint} to extract page {page_number}")
        # freeze current page to pdf
        fp = save_page_to_pdf(document, page_number, output_dir)
        try:
            with open(
                fp, "rb"
            ) as f:  # Use 'with' to ensure the file is closed properly
                files = {"file": f}
                ocr_response = requests.post(endpoint, files=files, timeout=300)
                page_text = ocr_response.text

        except Exception as e:
            print(f"ERROR: {e}")
            page_text = ""

        try:
            os.remove(fp)  # Clean up the uploaded file
        except Exception as e:
            print(f"There was an error with file cleanup: \n{e}")

    # use regular text extraction when OCR is not needed
    else:
        page_text = page.get_text("text", sort=True)

    return page_number, page_text, tables, images


# reassemble page according to correct page order
def assemble_page_text(page_indices, page_texts):
    # Create a dictionary mapping page indices to their corresponding texts
    index_to_text = dict(zip(page_indices, page_texts))

    # Sort the keys (page indices) and use them to retrieve the correct order of texts
    sorted_texts = [index_to_text[i] for i in sorted(index_to_text.keys())]

    # Join the retrieved texts together
    assembled_text = " ".join(sorted_texts)

    return assembled_text


# threaded page extraction
def parse_fast(
    document,
    format: str,
    gr: float = 0.2,
    extract_tables: bool = True,
    extract_images: bool = True,
    endpoint: str = "https://ocr.insight.uidaho.edu/ocr",
    out_path: str = ",/output",
    **kwargs,
):
    tables = {}
    images = {}
    page_order = []
    page_text = []

    with ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(
                process_page,
                document,
                page,
                gr,
                extract_tables,
                extract_images,
                endpoint,
                out_path,
                **kwargs,
            ): page
            for index, page in enumerate(range(document.page_count))
        }
        for future in as_completed(futures):
            pn, text, tdict, idict = future.result()

            page_order.append(pn)
            page_text.append(text)
            tables = tables | tdict
            images = images | idict

    all_text = assemble_page_text(page_indices=page_order, page_texts=page_text)

    try:
        if format == "plain text":
            return all_text, tables, images
        elif format == "markdown":
            markdown_text = md(
                all_text,
                escape_underscores=False,
                escape_all=False,
                strip=["a", "span"],
            )
        return clean_markdown(markdown_text), tables, images
    except Exception as e:
        print(f"ERROR {e}")


def parse_fast_by_page(
    document,
    format: str,
    gr: float = 0.2,
    extract_tables: bool = True,
    extract_images: bool = True,
    endpoint: str = "https://ocr.insight.uidaho.edu/ocr",
    out_path: str = "./output",
    **kwargs,
):
    tables = {}
    images = {}
    page_order = []
    page_texts = []  # Store text page by page

    with ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(
                process_page,
                document,
                page,
                gr,
                extract_tables,
                extract_images,
                endpoint,
                out_path,
                **kwargs,
            ): page
            for page in range(document.page_count)
        }

        for future in as_completed(futures):
            pn, text, tdict, idict = future.result()
            page_order.append(pn)
            page_texts.append((pn, text))  # Store each page's text with page number
            tables = tables | tdict
            images = images | idict

    # Sort page_texts based on page numbers to maintain order
    page_texts.sort(key=lambda x: x[0])
    sorted_texts = [text for _, text in page_texts]  # Extract sorted texts only

    try:
        if format == "plain text":
            return (
                sorted_texts,
                tables,
                images,
            )  # Return list of page texts instead of merged text
        elif format == "markdown":
            markdown_texts = [
                md(
                    text,
                    escape_underscores=False,
                    escape_all=False,
                    strip=["a", "span"],
                )
                for text in sorted_texts
            ]
            cleaned_texts = [clean_markdown(md_text) for md_text in markdown_texts]
            return cleaned_texts, tables, images
    except Exception as e:
        print(f"ERROR {e}")
