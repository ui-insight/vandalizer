from typing import Optional

import requests

# for dev
HOST_URL = "http://processpdf.nkn.uidaho.edu"

# for local
# HOST_URL = 'http://localhost:5019'

# for prod
# HOST_URL = 'https://processpdf.insight.uidaho.edu'

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

valid_ocr_methods = ["ocr", "doctr", "easyocr", "olmocr", "tesseract", "smoldocling"]


# The UIPDF class for document extraction
class UIPDF:
    """
    The UIPDF class provides high-level interfaces for extracting text and tables from PDF documents
    using both local OCR (Optical Character Recognition) methods and remote vision-language model (VLM) APIs.

    Key Features:
    -------------
    - Supports a variety of OCR engines (e.g., Tesseract, EasyOCR, Doctr) and VLM-based extraction methods.
    - Offers simple static methods for extracting full text or tables from PDFs with minimal configuration.
    - Allows asynchronous processing via webhook callbacks or synchronous extraction with immediate return.
    - Supports output in multiple formats (plain text, markdown, HTML, CSV) for tables.

    Main Usage Modes:
    -----------------
    1. **Text Extraction (`convert_to_text`)**:
        - Extracts all or specified pages' text from a PDF file.
        - Allows selection of OCR/VLM method.
        - Can operate synchronously or asynchronously (with `webhook_url`).
        - Returns the extracted text as a string if successful.

    2. **Table Extraction (`convert_table`)**:
        - Extracts a table from a specific page in a PDF file.
        - Allows selection of OCR/VLM method and output format (markdown, HTML, CSV).
        - Returns the extracted table as a string if successful.

    Methods:
    --------
    - `convert_to_text(file_path, method, webhook_url, only_these_pages)`:
        Extracts text from a PDF using the specified OCR or VLM method.
    - `convert_table(file_path, page_number, method, webhook_url, table_format)`:
        Extracts a table from a specific page in a PDF in the desired format.

    Notes:
    ------
    - The class is designed to be used with both local and remote PDF processing pipelines.
    - Refer to individual method docstrings for detailed arguments, return values, and exceptions.

    Example:
    --------
        # Extract all text from a PDF
        text = UIPDF.convert_to_text(
            file_path="./mydoc.pdf",
            method="qwen2.5-VL-8k:7b"
        )

        # Extract a table from page 2 in markdown format
        table_md = UIPDF.convert_table(
            file_path="./sample.pdf",
            page_number=2,
            method="qwen2.5-VL-8k:7b",
            table_format="markdown"
        )
    """

    @staticmethod
    def convert_to_text(
        file_path: str = "./path/to/your/file.pdf",
        method: Optional[str] = None,
        webhook_url: Optional[str] = None,
        only_these_pages: Optional[str] = None,
    ):
        """
        Converts a PDF file to text using an OCR or VLM method via an API endpoint.

        This function uploads a PDF file to a remote API for text extraction using the specified OCR or VLM method.
        The extracted text is returned if the operation is successful.

        Args:
            file_path (str):
                The path to the PDF file to be processed. Defaults to './path/to/your/file.pdf'.
            method (Optional[str]):
                The OCR or VLM method to use for text extraction. If not specified, defaults to 'qwen2.5-VL-8k:7b'.
                Must be in the list of valid OCR or VLM methods.
            webhook_url (Optional[str]):
                If provided, the API will send asynchronous job status and results to this URL. If not provided, the
                function will fetch the result synchronously.
            only_these_pages (Optional[str]):
                A comma-separated string of page numbers to process (e.g., "1,3,5"). If None, all pages are processed.

        Returns:
            str or None: The extracted text if successful, otherwise None. Returns an empty string if the file is not found.

        Raises:
            ValueError: If the specified method is invalid.

        Example:
            >>> text = UIPDF.convert_to_text(
            ...     file_path="./mydoc.pdf",
            ...     method="qwen2.5-VL-8k:7b"
            ... )
            >>> print(text)
        """

        try:
            file = {"file": open(file_path, "rb")}
        except FileNotFoundError:
            return ""

        if not method:
            method = "qwen2.5-VL-8k:7b"
            print(f"Method not specified, using default {method}")

        params = {
            "format": "markdown",
            "return_document_as": "merged_text",
            "extract_images": "false",
            "extract_tables": "false",
        }

        if method in valid_ocr_methods:
            _type = "ocr"
            params["ocr_tool"] = method
        elif method in valid_vlm_methods:
            _type = "vlm"
            params["vlm_name"] = (method,)
        else:
            raise ValueError(f"Invalid method: {method}")

        params["tool_type"] = _type
        if webhook_url:
            params["webhook_url"] = webhook_url
            endpoint = f"{HOST_URL}/api/v1/start-job"
        else:
            if _type == "ocr":
                endpoint = f"{HOST_URL}/api/v1/ExtractPDF"
            elif _type == "vlm":
                endpoint = f"{HOST_URL}/api/v1/AIExtractPDF"

        try:
            response = requests.post(url=endpoint, params=params, files=file)
            if response.status_code == 200:
                response_dict = response.json()
                return response_dict["text"]
            else:
                print("SERVER ERROR")
                print(response.status_code)
                print(response.text)
                return None
        except requests.RequestException as e:
            print(f"Error occurred while converting PDF: {e}")
            return None

    @staticmethod
    def convert_table(
        file_path: str = "./path/to/your/file.pdf",
        page_number: int = None,
        method: Optional[str] = None,
        webhook_url: Optional[str] = None,
        table_format: Optional[str] = None,
    ):
        """
        Extracts a table from a specific page of a PDF file using the specified OCR or VLM method via an API endpoint.

        This function uploads a PDF file to a remote API and extracts a table from the given page number
        in the desired format (markdown, HTML, or CSV). The extracted table is returned as text.

        Args:
            file_path (str):
                The path to the PDF file to be processed. Defaults to './path/to/your/file.pdf'.
            page_number (int):
                The 1-based index of the page to extract the table from. (Required)
            method (Optional[str]):
                The OCR or VLM method to use for table extraction. If not specified, defaults to 'qwen2.5-VL-8k:7b'.
                Must be present in the list of valid OCR or VLM methods.
            webhook_url (Optional[str]):
                If provided, the API may send asynchronous job status and results to this URL. (Currently not used in this method.)
            table_format (Optional[str]):
                Output format for the table. Must be one of 'markdown', 'html', or 'csv'. Defaults to 'markdown'.

        Returns:
            str or None: The extracted table as text if successful, otherwise None.
            Returns an empty string if the file is not found.

        Raises:
            ValueError: If the specified method or table_format is invalid, or if page_number is not specified.

        Example:
            >>> table_md = MyClass.convert_table(
            ...     file_path="./sample.pdf",
            ...     page_number=2,
            ...     method="qwen2.5-VL-8k:7b",
            ...     table_format="markdown"
            ... )
            >>> print(table_md)
        """

        try:
            file = {"file": open(file_path, "rb")}
        except FileNotFoundError:
            return ""

        if not method:
            method = "qwen2.5-VL-8k:7b"
            print(f"Method not specified, using default {method}")

        if not table_format:
            table_format = "markdown"
        else:
            if table_format not in ["markdown", "html", "csv"]:
                raise ValueError(
                    f'ERROR: table_format must be one of markdown, html, or csv - not "{table_format}"'
                )

        if not page_number:
            raise ValueError("ERROR: page_number must be specified")
        else:
            pn = page_number - 1

        params = {
            "detection_threshold": 0.5,
            "page_number": pn,
            "format": table_format,
        }

        if method in valid_ocr_methods:
            _type = "ocr"
            params["ocr_tool"] = method
        elif method in valid_vlm_methods:
            _type = "vlm"
            params["vlm_name"] = (method,)
        else:
            raise ValueError(f"Invalid method: {method}")

        params["tool_type"] = _type
        endpoint = f"{HOST_URL}/api/v1/ExtractTable"

        try:
            response = requests.post(url=endpoint, params=params, files=file)

            if response.status_code == 200:
                response_dict = response.json()
                return response_dict["text"]
            else:
                print("SERVER ERROR")
                print(response.status_code)
                print(response.text)
                return None
        except requests.RequestException as e:
            print(f"Error occurred while converting PDF: {e}")
            return None
