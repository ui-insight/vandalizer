import ast
import os

# import easyocr
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from typing import Dict, List, Optional

import fitz
import pytesseract
import requests
from markdownify import markdownify as md
from pdf2image import convert_from_path
from PIL import Image
from tqdm import tqdm

# for dev
# HOST_URL = 'http://processpdf.nkn.uidaho.edu'

# for local
# HOST_URL = 'http://localhost:5019'

# for prod
HOST_URL = "https://processpdf.insight.uidaho.edu"

valid_vlm_methods = [
    "gemma3-64k:27b",
    "llama3.2-vision:11b",
    "llama3.2-vision:90b",
    "mistralai/pixtral-large-2411",
    "mistralai/pixtral-12b",
    "google/gemini-pro-1.5",
    "google/gemini-2.0-flash-lite-001",
    "microsoft/phi-4-multimodal-instruct",
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "granite3.2-vision-16k:2b",
    "qwen2.5-VL-8k:7b",
]

valid_ocr_methods = [
    "ocr",
    "doctr",
    #'easyocr',
    "olmocr",
    "tesseract",
    "smoldocling",
]


def clean_markdown(text):
    text = re.sub(r"\\(\d+\.)", r"\1", text)
    text = re.sub(r"\\([\.#\-_])", r"\1", text)
    text = re.sub(r"\\([\$\+])", r"\1", text)
    return text


def sort_pages(lst: List[int]):
    # Get the sorted order of indices
    order = sorted(range(len(lst)), key=lambda i: lst[i])
    # Use the order to get the sorted list
    sorted_list = [lst[i] for i in order]
    return sorted_list, order


def is_full_page_image(page: int, coverage_threshold: float = 0.9):
    page_rect = fitz.Rect(page.rect)  # rectangle of the page in points
    page_area = page_rect.width * page_rect.height

    # Parse page display list to find image drawing commands and their rects
    img_areas = 0.0
    for img in page.get_image_info():
        bbox = fitz.Rect(img["bbox"])
        # print('image width: ', bbox.width)
        # print('image height: ', bbox.height)
        img_areas += bbox.width * bbox.height

    # Calculate coverage ratio
    coverage = img_areas / page_area
    if coverage >= coverage_threshold:
        decision = True
    else:
        decision = False
    return decision, coverage


# helper function to estimate extraction confidence using tesseract
def get_page_confidence(page_obj: fitz.Page, page_num: int):
    if isinstance(page_obj, str):
        page_image = convert_from_path(page_obj)
    elif isinstance(page_obj, BytesIO):
        page_image = Image.open(page_obj)
    else:
        raise ValueError("Unsupported type for page_obj")

    df = pytesseract.image_to_data(page_image, output_type="data.frame")
    # page_df = [pytesseract.image_to_data(im, output_type='data.frame') for im in page_images]
    # page_dfs_numbered = [df.assign (page_num=npage) for npage, df in enumerate(page_dfs)]
    # df = pd.concat(page_dfs_numbered, ignore_index=True)
    # average_conf_per_block = df[df['conf'] != -1].groupby('page_num')['conf'].mean()
    page_conf = df[df["conf"] != -1].groupby("block_num")["conf"].mean().min()
    return page_conf


def cat_single_page(doc, page_number):
    try:
        thispage = doc[page_number]
        pagebytes = BytesIO(thispage.get_pixmap().tobytes("ppm"))
        decision, coverage = is_full_page_image(page=thispage)

        if decision:
            print("-" * 30)
            # print(f"Page {page_number} has coverage {(coverage*100):.4f} Decision: {decision}")
            return (page_number, None, decision)
        else:
            confidence = get_page_confidence(page_obj=pagebytes, page_num=page_number)
            # print(f"minimum block confidence for page {page_number}: {confidence:.4f}")
            return (page_number, confidence, decision)

    except Exception as e:
        print(f"Error categorizing page {page_number}: {e}")
        return (page_number, None, None)


# categorizes the difficulty of pages based on their confidence score and image span
def categorize_pages(pdf_path: str, min_block_thresh: float = 60.0):
    doc = fitz.open(pdf_path)
    page_count = doc.page_count
    hard_pages = []
    easy_pages = []

    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = [
            executor.submit(cat_single_page, doc, page) for page in range(page_count)
        ]
        for future in as_completed(futures):
            try:
                page_number, confidence, decision = future.result()
                if decision:
                    hard_pages.append((page_number, None, decision))
                else:
                    if confidence < min_block_thresh:
                        hard_pages.append((page_number, confidence, decision))
                    else:
                        easy_pages.append((page_number, confidence, decision))
            except Exception as e:
                print(f"Error categorizing page {page_number}: {e}")
                hard_pages.append((page_number, None, None))

    return {"hard_pages": hard_pages, "easy_pages": easy_pages}


# a helper function to extract text from document page using easyOCR
# def process_page_easyocr(image: Image.Image, npage: int, reader: easyocr.Reader):

#     try:
#         print(f"--- Page {npage + 1} ---")
#         bytes_io = BytesIO()
#         # Save the image to the BytesIO object in PPM format
#         image.save(bytes_io, format='PPM')
#         # Get the byte data
#         image_bytes = bytes_io.getvalue()
#         # Close the BytesIO object
#         bytes_io.close()
#         # Use easyocr to read the text from the image
#         results = reader.readtext(image_bytes)#, rotation_info=[90, 180 ,270])
#         text_list = [text for _, text, _ in results]
#         page_text = ' '.join(text_list)

#         print(f'Extracted text: \n {page_text[:500]}')
#         return page_text.strip(), npage
#     except Exception as e:
#         print(f"Error extracting text: {e}")
#         return ""


# A helper function to extract text from document page using tesseract
def process_page_tesseract(image: Image.Image, npage: int, **kwargs):
    try:
        print(f"--- Page {npage + 1} ---")
        page_text = pytesseract.image_to_string(image, timeout=300, **kwargs)
        print(f"Extracted text: \n {page_text[:200]}")
        return page_text.strip(), npage
    except Exception as e:
        print(f"Error extracting text on page {npage}: {e}")
        return ""


# Threaded extraction of document pages using tesseract OCR.
def extract_with_tesseract(
    pdf_path,
    which_pages: List[int] = None,
    return_as_pages: bool = False,
    format: str = "markdown",
    **kwargs,
):
    """
    Extracts text from a PDF using Tesseract OCR.
    """
    success = 200
    try:
        page_texts = []
        print(f"Converting pages from @{pdf_path} with tesseract OCR")
        # Convert PDF to images
        images = convert_from_path(pdf_path)
        if which_pages:
            images = [images[i] for i in which_pages]
        # Iterate over the images and extract text
        with ThreadPoolExecutor(max_workers=16) as executor:
            futures = {
                executor.submit(process_page_tesseract, page, index, **kwargs): page
                for index, page in enumerate(images)
            }
            for future in as_completed(futures):
                page_text, pn = future.result(timeout=300)
                page_texts.append((pn, page_text))

        page_texts.sort(key=lambda x: x[0])
        sorted_texts = [text for _, text in page_texts]

        try:
            if format == "plain text":
                cleaned_texts = (sorted_texts,)
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
            else:
                raise ValueError(
                    "Invalid format specified. Supported formats are 'plain text' and 'markdown'."
                )
        except Exception as e:
            print(f"ERROR {e}")

        if return_as_pages:
            return cleaned_texts, success
        else:
            return "\n\n".join(cleaned_texts), success

    except Exception as e:
        print(f"Error extracting text from @{pdf_path}: \n {e}")
        return "", 500


# extraction using easyOCr
# def extract_with_easyocr(pdf_path: str, **kwargs):
#     """
#     Extracts text from a PDF using EasyOCR OCR.
#     """
#     success = 200
#     try:
#         page_texts = []
#         print(f'Converting pages from @{pdf_path} with EasyOCR')
#         # Convert PDF to images
#         images = convert_from_path(pdf_path)

#         # Initialize the easyocr Reader for English (you can add more languages if needed)
#         OCRreader = easyocr.Reader(['en'], **kwargs)
#         for index, im in enumerate(images):
#             try:
#                 page_text, pn = process_page_easyocr(image = im,
#                                                     npage=index,
#                                                     reader=OCRreader)

#                 page_texts.append(f'Page Number {pn} \n\n' +page_text)
#             except Exception as e:
#                 print(f'Error processing page {index}: {e}')
#                 continue

#         return '\n\n'.join(page_texts), success
#     except Exception as e:
#         print(f'Error unable to parse document {e}')
#         return '', 500


# Helper function to check if tesseract is available on host machine
def check_and_set_tesseract(user_tesseract_path: str = "/opt/homebrew/bin/tesseract"):
    """
    Checks if the provided Tesseract path is valid and sets it if not.
    """
    # List of common tesseract executable paths to check
    common_paths = [
        "/opt/homebrew/bin/tesseract",  # macOS Homebrew (Apple Silicon)
        "/usr/local/bin/tesseract",  # macOS Homebrew (Intel)
        "/usr/bin/tesseract",  # Linux default
        "C:\\Program Files\\Tesseract-OCR\\tesseract.exe",  # Windows default 64-bit
        "C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe",  # Windows default 32-bit
    ]

    if user_tesseract_path not in common_paths:
        common_paths = common_paths.append(user_tesseract_path)

    # Also check if tesseract is in PATH
    tesseract_in_path = shutil.which("tesseract")
    if tesseract_in_path:
        pytesseract.pytesseract.tesseract_cmd = tesseract_in_path
        return

    # Check the common paths
    for path in common_paths:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            pytesseract.pytesseract.tesseract_cmd = path
            return

    raise EnvironmentError(
        f"""Tesseract executable not found at any of these known locations:
        
        {"\n".join(common_paths)}
        
        Please set the path manually with 'user_tesseract_path=your_path_here' or refer to https://github.com/tesseract-ocr/tesseract for installation instructions.
        """
    )


# The UIPDF class for document extraction
class UIPDF:
    """
    The UIPDF class provides high-level and low-level interfaces for PDF document text extraction
    using both local OCR (Optical Character Recognition) methods and remote vision-language model (VLM) APIs.

    Key Features:
    -------------
    - Supports a variety of OCR engines (e.g., Tesseract, EasyOCR, Doctr) and VLM-based extraction methods.
    - Allows both fine-grained control (via `process_pdf`) and automatic, user-friendly extraction (via `convert_to_text`).
    - Enables hybrid extraction by categorizing pages as "easy" or "hard" and using the appropriate OCR method for each.
    - Provides job-based asynchronous processing for large PDFs, with built-in progress tracking and result retrieval.

    Main Usage Modes:
    -----------------
    1. **Direct Processing (`process_pdf`)**:
        - For users needing control over extraction parameters.
        - Allows specification of OCR/VLM method, return format, subset of pages, and other parameters.
        - See API documentation at: http://processpdf.nkn.uidaho.edu/apidocs/

    2. **Automatic Extraction (`convert_to_text`)**:
        - For users wanting a simplified workflow.
        - Automatically detects which pages are suitable for fast local OCR and which require robust API processing.

    3. **Job-based Processing (`start_job`, `get_status`, `retrieve_result`, `run_ocr_job`)**:
        - For handling large documents or asynchronous/cloud-based extraction.
        - Supports job submission, progress polling, and final result retrieval.

    Methods:
    --------
    - `process_pdf`: Extracts text from PDF using specified OCR or VLM method and options.
    - `convert_to_text`: Automatically classifies pages and applies the best OCR strategy for each.
    - `start_job`: Submits a PDF for asynchronous processing to the remote API.
    - `get_status`: Polls job status and progress from the API.
    - `retrieve_result`: Retrieves the final results of a completed job.
    - `run_ocr_job`: End-to-end workflow for asynchronous OCR with progress bar support.

    Notes:
    ------
    - The class is designed to be used with both local and remote PDF processing pipelines.
    - Refer to individual method docstrings for detailed arguments, return values, and exceptions.

    Example:
    --------
        # Direct processing
        text = UIPDF.process_pdf(pdf_path="doc.pdf", method="tesseract", return_as="pages")

        # Automatic extraction
        text = UIPDF.convert_to_text(url="doc.pdf")

        # Job-based processing
        job_id, start_time = UIPDF.start_job(params, files)
        while True:
            status = UIPDF.get_status(job_id)
            # ... polling logic ...
        result = UIPDF.retrieve_result(job_id)
    """

    @staticmethod
    def process_pdf(
        pdf_path: str = "./path/to/your/file.pdf",
        method: Optional[str] = "doctr",
        return_as: Optional[str] = ["pages", "merged_text"],
        user_tesseract_path: Optional[str] = "/opt/homebrew/bin/tesseract",
        pages_to_extract: List[int] = None,
        text_format: Optional[str] = "markdown",
        **kwargs,
    ):
        """
        Convert a PDF file to text using the specified OCR or VLM method.

        The method supports multiple OCR engines (e.g., tesseract, easyocr, doctr, etc) and VLM-based extraction.
        It sends the PDF to appropriate API endpoints for processing or uses local OCR tools.
        Supports extracting specific pages and returning results either per page or merged.

        Args:
            pdf_path (str): Path to the input PDF file. Defaults to './path/to/your/file.pdf'.
            method (str):
                OCR or VLM extraction method to use.
                Must be one of the supported methods (e.g., 'tesseract', 'easyocr', 'doctr', or VLM names).
                Defaults to 'doctr'.
            return_as (str):
                Format of the extracted text return value.
                Either 'pages' (list of page texts) or 'merged_text' (single concatenated string).
                Defaults to 'pages'.
            user_tesseract_path (str):
                Filesystem path to the Tesseract executable. Used if method is 'tesseract'.
                Defaults to '/opt/homebrew/bin/tesseract'.
            pages_to_extract (list[int], optional): List of page numbers (0-indexed) to extract.
                If None, extracts all pages.
            text_format (str, optional):
                Format of the extracted text.
                Defaults to 'markdown'. Other formats includ "plain text".
            **kwargs: Additional keyword arguments forwarded to OCR extraction functions.

        Returns:
            Union[list[str], str, None]:
                Extracted text as a list of pages or merged string depending on `return_as`.
                Returns None if an error occurs.

        Raises:
            ValueError: If `return_as` is not 'pages' or 'merged_text'.
            ValueError: If `method` is not in supported OCR or VLM methods.
        """

        if isinstance(return_as, str):
            if return_as not in ["pages", "merged_text"]:
                raise ValueError(
                    "Invalid return_as value. Must be either 'pages' or 'merged_text'."
                )

        elif isinstance(return_as, list):
            raise ValueError(
                "Invalid return_as value. Must be either 'pages' or 'merged_text'."
            )

        params = {
            "format": text_format,
            "return_document_as": return_as,
            "extract_tables": False,
            "extract_images": False,
            "pages_to_extract": str(pages_to_extract) if pages_to_extract else None,
        }

        if method in valid_ocr_methods:
            _type = "ocr"
            params["ocr_tool"] = method
        elif method in valid_vlm_methods:
            _type = "vlm"
            params["vlm_name"] = (method,)
        else:
            raise ValueError(f"Invalid method: {method}")

        if _type == "ocr":
            endpoint = f"{HOST_URL}/api/v1/ExtractPDF"
        elif _type == "vlm":
            endpoint = f"{HOST_URL}/api/v1/AIExtractPDF"

        if method in ["tesseract", "easyocr"]:
            if method == "tesseract":
                check_and_set_tesseract(user_tesseract_path=user_tesseract_path)
                text, status = extract_with_tesseract(
                    pdf_path=pdf_path, format=text_format, **kwargs
                )

            # elif method == 'easyocr':
            #     text, status = extract_with_easyocr(pdf_path=pdf_path, **kwargs)

            if status == 200:
                return text
            else:
                print(f"Error occurred while converting PDF with {method}: {status}")
                return None

        try:
            files = {"file": open(pdf_path, "rb")}
            response = requests.post(url=endpoint, params=params, files=files)
            if response.status_code == 200:
                response_dict = response.json()
                if return_as == "pages":
                    return ast.literal_eval(response_dict["text"])
                elif return_as == "merged_text":
                    return response_dict["text"]
            else:
                print("SERVER ERROR")
                print(response.status_code)
                print(response.text)
                return None
        except Exception as e:
            print(f"Error occurred while converting PDF: {e}")
            return None

    @staticmethod
    def convert_to_text(
        url: str = "./path/to/your/file.pdf", method: Optional[str] = None
    ):
        """
        Quickly extract text from a PDF by intelligently combining fast and robust OCR methods in parallel.

        This method analyzes the given PDF file to classify pages into 'easy' and 'hard' categories based
        on their content characteristics (e.g., text density, image coverage). It then applies a fast OCR
        approach (Tesseract) on the 'easy' pages and a more robust OCR method (configurable by the user) on
        the 'hard' pages concurrently to maximize processing speed and accuracy.

        The results from both OCR strategies are merged and sorted to preserve original page order before
        returning the full extracted text.

        Parameters:
            url (str):
                Path to the PDF file to process. Defaults to './path/to/your/file.pdf'.
            method (str, optional):
                The OCR method or model identifier to use for 'hard' pages requiring robust OCR.
                If not provided, defaults to 'google/gemini-2.0-flash-lite-001'.

        Returns:
            str:
                The complete extracted text from the PDF, concatenated in the correct page order.
                Returns an empty string if no text could be extracted.

        Raises:
            RuntimeError:
                If page categorization fails, an exception is raised with the underlying error details.

        Behavior and Implementation Details:
            - Uses `categorize_pages` to classify pages into 'easy' and 'hard' based on content.
            - Runs `extract_with_tesseract` on 'easy' pages using a thread pool internally.
            - Runs `UIPDF.process_pdf` with the specified robust OCR method on 'hard' pages.
            - Handles exceptions gracefully and logs errors without failing silently.
            - If either OCR method fails or returns no text, proceeds with whatever text is available.
            - Sorts the combined extracted texts by page number to maintain original document order.

        Notes:
            - This method is designed to maximize throughput by leveraging concurrency and tailored OCR per page.
            - The default robust OCR method is intended for pages with complex layouts or poor scan quality.

        Example:
            >>> text = UIPDF.quick_convert("document.pdf")
            >>> print(text)
        """
        full_text = []
        full_page_order = []
        easy_pages = None
        hard_pages = None

        if not method:
            method = "tesseract"

        try:
            page_cats = categorize_pages(pdf_path=url, min_block_thresh=70.0)
        except Exception as e:
            raise RuntimeError("Page categorization failed") from e

        if len(page_cats["easy_pages"]) > 0:
            print("Parsing easy pages with Tesseract ...")
            easy_pages = [i[0] for i in page_cats.get("easy_pages", [])]
            try:
                tesseract_pages, tess_status = extract_with_tesseract(
                    pdf_path=url, which_pages=easy_pages, return_as_pages=True
                )
                if easy_pages and tess_status == 200:
                    full_text.extend(tesseract_pages)
                    full_page_order.extend(easy_pages)
                    print("Done!")
                else:
                    raise UserWarning(
                        "Tesseract OCR returned no valid text or error status."
                    )
            except Exception as e:
                print(f"Tesseract extraction failed: {e}")
                full_text.extend("")

        if len(page_cats["hard_pages"]) > 0:
            print("Submitting API request for hard pages...")
            hard_pages = [i[0] for i in page_cats.get("hard_pages", [])]
            try:
                api_pages = UIPDF.process_pdf(
                    pdf_path=url,
                    method=method,
                    return_as="pages",
                    pages_to_extract=hard_pages,
                )
                if api_pages and hard_pages:
                    hard_pages.sort()
                    full_text.extend(api_pages)
                    full_page_order.extend(hard_pages)
                    print("done!")
            except Exception as e:
                print(f"API extraction failed: {e}")
                full_text.extend("")

        if len(full_text) < 0:
            raise RuntimeError("Text extraction failed")
        else:
            if easy_pages:
                _, page_index = sort_pages(full_page_order)
                sorted_text = [full_text[i] for i in page_index]
                return "\n\n".join(sorted_text)
            else:
                return "\n\n".join(full_text)

    @staticmethod
    def start_job(params: Dict[str, str], files: object):
        """
        Submit a new processing job to the API.

        Args:
            params (dict): Dictionary of query parameters for the API request.
            params = {
                    'format': 'markdown',
                    'tool_type': 'ocr',
                    'ocr_tool': 'doctr',
                    'vlm_name': 'google/gemini-2.0-flash-exp:free',
                    'return_document_as': 'pages',
                    'garbleRatio': 0.2,
                    'extract_tables': 'false',
                    'extract_images': 'false',
                    'pages_to_extract': '[1,2,3]'
                }
            files (dict): Dictionary of files to upload, e.g. {'file': open('path.pdf', 'rb')}.

        Returns:
            str or None: The job ID if submission was successful, or None if there was an error.

        Example:
            >>> job_id = start_job(params={'foo': 'bar'}, files={'file': open('doc.pdf', 'rb')})
        """

        url = f"{HOST_URL}/api/v1/start-job"
        try:
            response = requests.post(url, params=params, files=files)
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "Unknown"
            if status == 400:
                print(f"Submission failed: {e.response.text if e.response else e}")
            elif status == 500:
                print(f"Server error (500): {e.response.text if e.response else e}")
            else:
                print(f"HTTP error ({status}): {e}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            return None

        try:
            data = response.json()
        except ValueError:
            print("Failed to parse response as JSON.")
            return None

        job_id = data.get("job_id")
        if not job_id:
            print("No job_id returned in response.")
            return None

        print(f"Started job with ID: {job_id}")
        return job_id, time.time()  # or (job_id, data) if you want more details

    @staticmethod
    def get_status(job_id: str):
        """
        Retrieve the final result of a completed job.

        Args:
            job_id (str): The job ID whose result is to be retrieved.

        Returns:
            dict or None: Result data as a dictionary if successful, or None if not available or there was an error.

        Example:
            >>> completed_pages = get_status(job_id="abcdefg-12345")['progress']
        """
        url = f"{HOST_URL}/api/v1/job-status/{job_id}"
        try:
            response = requests.get(url)
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            # Prefer to get status code from the response attached to the exception if possible
            status_code = e.response.status_code if e.response else None
            if status_code == 404:
                print(f"Job with id {job_id} not found.")
            elif status_code == 500:
                print("Server error. Unable to retrieve job status.")
            else:
                print(f"HTTP {status_code} error occurred: {e}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"Network or connection error occurred: {e}")
            return None

        try:
            data = response.json()
        except ValueError:
            print("Failed to parse response as JSON.")
            return None

        return data

    @staticmethod
    def retrieve_result(job_id: str):
        """
        Retrieve the final result of a completed job.

        Args:
            job_id (str): The id of the job to be retreived

        Returns:
            dict or None: Result data as a dictionary if successful, or None if not available or there was an error.

        Example:
            >>> parsed_text = retreive_result(job_id="abcdefg-12345")['text']
            >>> print(parsed_text)
            "The quick brown fox jumps over the lazy dog."
        """
        url = f"{HOST_URL}/api/v1/job-result/{job_id}"
        # send request and parse possible errors
        try:
            response = requests.get(url)
            response.raise_for_status()

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else None
            if status_code == 404:
                print(
                    "Job result not found. Job may still be running or does not exist."
                )
            elif status_code == 500:
                print("Server error. Please try again later.")
            else:
                print(f"HTTP error occurred: {e}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"Network or connection error occurred: {e}")
            return None

        # parse response
        try:
            return response.json()
        except ValueError:
            print("Failed to parse response as JSON.")
            return None

    @staticmethod
    def run_ocr_job(url: str = "./path/to/your/file.pdf", method: str = None):
        """
        Run an OCR job on a PDF file, processing "easy" pages locally with Tesseract and "hard" pages via an external API.

        This function:
          - Opens the PDF and determines the number of pages.
          - Categorizes pages into "easy" (suitable for Tesseract OCR) and "hard" (requiring VLM/remote OCR).
          - Processes easy pages locally using Tesseract.
          - Submits hard pages to an OCR/VLM API as a job and polls for job completion, displaying a progress bar.
          - Retrieves and returns the OCR results upon completion.

        Args:
            url (str): Path to the PDF file to process.
            method (str, optional): OCR or VLM method name. Must be in `valid_ocr_methods` or `valid_vlm_methods`.
                If None, defaults to `'google/gemini-2.0-flash-lite-001'`.

        Returns:
            dict or None: The result data from the OCR job if successful, or None if there was an error.

        Raises:
            ValueError: If the provided method is not valid.
            RuntimeError: If page categorization fails.

        Example:
            # Make sure valid_ocr_methods, valid_vlm_methods, categorize_pages, extract_with_tesseract,
            # and UIPDF.start_job / get_status / retrieve_result are defined and imported.

            result = UIPDF.run_ocr_job(
                url='./my_scan.pdf',
                method='google/gemini-2.0-flash-lite-001'
            )
            if result:
                print("OCR result:", result)
            else:
                print("OCR job failed or was incomplete.")
        """

        full_text = []
        full_page_order = []
        easy_pages = None
        hard_pages = None

        try:
            doc = fitz.open(url)
            total_pages = doc.page_count
        except Exception as e:
            print(f"Error opening PDF: {e}")
            return None

        if not method:
            method = "tesseract"

        try:
            page_cats = categorize_pages(pdf_path=url, min_block_thresh=70.0)
        except Exception as e:
            raise RuntimeError("Page categorization failed") from e

        if len(page_cats["easy_pages"]) > 0:
            print("parsing easy pages with Tesseract OCR...")
            easy_pages = [i[0] for i in page_cats.get("easy_pages", [])]
            try:
                tesseract_pages, tess_status = extract_with_tesseract(
                    pdf_path=url, which_pages=easy_pages, return_as_pages=True
                )
                if easy_pages and tess_status == 200:
                    full_text.extend(tesseract_pages)
                    full_page_order.extend(easy_pages)
                    print("Tesseract extraction successful...")
                else:
                    raise UserWarning(
                        "Tesseract OCR returned no valid text or error status."
                    )
            except Exception as e:
                print(f"Tesseract extraction failed: {e}")
                full_text.extend("")

        if len(page_cats["hard_pages"]) > 0:
            hard_pages = [i[0] for i in page_cats.get("hard_pages", [])]

            # Query parameters
            params = {
                "format": "markdown",
                "return_document_as": "pages",
                "extract_images": "false",
                "extract_tables": "false",
                "pages_to_extract": str(hard_pages),
            }

            # handle parameters for OCR or VLM
            if method in valid_ocr_methods:
                _type = "ocr"
                params["ocr_tool"] = method
                params["ocr_type"] = _type
            elif method in valid_vlm_methods:
                _type = "vlm"
                params["vlm_name"] = method
                params["ocr_type"] = _type

            else:
                raise ValueError(
                    f"Invalid method: {method} must be one of \n\n{'\n'.join(valid_ocr_methods + valid_vlm_methods)}"
                )

            if method == "tesseract":
                raise ValueError(
                    'Tesseract is not supported for OCR jobs. If you want to use "tesseract" please use convert_to_text method.'
                )

            # submit job to API
            try:
                files = {"file": open(url, "rb")}
                job_id, start_time = UIPDF.start_job(params, files)
            except Exception as e:
                print(f"Job submission failed: {e}")
                return

            with tqdm(total=total_pages, desc="Processing pages") as bar:
                last_progress = 0
                while True:
                    status_data = UIPDF.get_status(job_id)
                    status = status_data.get("status")
                    progress = status_data.get("progress", 0)

                    # Only update the bar with the new pages since last update
                    bar.update(progress - last_progress)
                    bar.set_postfix_str(f"Job status: {status}")
                    last_progress = progress

                    if status == "finished":
                        end_time = time.time()
                        print(
                            f"\n\nJob completed in {((end_time - start_time) / 60):.2f} Minutes."
                        )
                        break
                    elif status == "failed":
                        print("Job failed.")
                        return
                    time.sleep(1)  # wait before polling again

            api_result = UIPDF.retrieve_result(job_id)
            api_pages = api_result.get("text", [])
            if api_pages and hard_pages:
                hard_pages.sort()
                full_text.extend(api_pages)
                full_page_order.extend(hard_pages)

                if len(full_text) < 0:
                    raise RuntimeError("Text extraction failed")
                    return
                else:
                    if easy_pages:
                        _, page_index = sort_pages(full_page_order)
                        sorted_text = [full_text[i] for i in page_index]
                        return "\n\n".join(sorted_text)
                    else:
                        return "\n\n".join(full_text)
