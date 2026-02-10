from typing import Optional

import requests

# Default OCR endpoint - can be overridden by system configuration
DEFAULT_HOST_URL = "https://processpdf.insight.uidaho.edu"


def get_host_url() -> str:
    """Get OCR endpoint from system configuration or use default."""
    try:
        from app.utilities.config import get_ocr_endpoint
        return get_ocr_endpoint()
    except Exception:
        return DEFAULT_HOST_URL


class UIPDF:
    """
    The UIPDF class provides an interface for extracting text from PDF documents
    by posting them to a configured OCR endpoint that returns markdown.
    """

    @staticmethod
    def convert_to_text(file_path: str) -> Optional[str]:
        """
        Converts a PDF file to markdown text by posting it to the configured OCR endpoint.

        Args:
            file_path (str): The path to the PDF file to be processed.

        Returns:
            str or None: The extracted markdown text if successful, None on error.
        """
        endpoint = get_host_url()
        try:
            with open(file_path, "rb") as f:
                response = requests.post(
                    url=endpoint,
                    files={"file": f},
                    headers={"Accept": "text/markdown"},
                )
            if response.status_code in [200, 201]:
                return response.text
            else:
                print(f"OCR SERVER ERROR: {response.status_code}")
                print(response.text)
                return None
        except FileNotFoundError:
            print(f"File not found: {file_path}")
            return None
        except requests.RequestException as e:
            print(f"Error calling OCR endpoint: {e}")
            return None

    @staticmethod
    def convert_to_text_demo(
        file_path: str = "./path/to/your/file.pdf", webhook_url: Optional[str] = None
    ) -> str:
        """
        Extract text from a PDF file using the configured OCR endpoint.

        Args:
            file_path (str): The path to the PDF file.
            webhook_url (Optional[str]): Unused, kept for backward compatibility.

        Returns:
            str: The extracted text from the PDF, or empty string on error.
        """
        result = UIPDF.convert_to_text(file_path)
        return result if result is not None else ""
