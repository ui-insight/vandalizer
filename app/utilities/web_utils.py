import re
import requests
import logging
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from typing import List, Dict, Optional, Set
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Set up a logger for clean and informative output.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class URLContentFetcher:
    """
    A robust class to find URLs in text, fetch their content, and extract
    clean, readable text from the HTML.
    """

    def __init__(self,
                 timeout: int = 15,
                 max_content_length: int = 100000,
                 user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"):
        """
        Initializes the URL content fetcher.

        Args:
            timeout: Request timeout in seconds.
            max_content_length: Maximum character length for extracted text content.
            user_agent: User agent string to use for HTTP requests.
        """
        self.timeout = timeout
        self.max_content_length = max_content_length
        self.session = self._create_session(user_agent)

    def _create_session(self, user_agent: str) -> requests.Session:
        """Creates a requests.Session with retry logic and browser-like headers."""
        session = requests.Session()

        # Set headers to mimic a real web browser, which can help avoid being blocked.
        session.headers.update({
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })

        # Implement a retry strategy for failed requests to handle transient network issues.
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],  # Retry on these status codes.
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def extract_urls(self, text: str) -> List[str]:
        """Extracts all unique URLs from a given text string."""
        # A more comprehensive regex to capture a wide variety of URL formats.
        url_pattern = re.compile(
            r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        )
        urls = url_pattern.findall(text)
        return list(set(urls)) # Return only unique URLs

    def _is_valid_url(self, url: str) -> bool:
        """Checks if a URL is well-formed and not a link to a non-text file."""
        try:
            parsed = urlparse(url)
            if not all([parsed.scheme, parsed.netloc]):
                return False

            # Avoid fetching large, non-HTML files.
            excluded_extensions: Set[str] = {
                '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
                '.zip', '.rar', '.exe', '.dmg', '.jpg', '.png', '.gif'
            }
            if any(parsed.path.lower().endswith(ext) for ext in excluded_extensions):
                logger.warning(f"Skipping URL with excluded file extension: {url}")
                return False

            return True
        except Exception:
            return False

    def _extract_title(self, soup: BeautifulSoup, url: str) -> str:
        """Extracts the page title using multiple fallback methods for reliability."""
        # Try finding the title in common meta tags or the main <h1> heading.
        title_selectors = [
            'title',
            'meta[property="og:title"]',
            'meta[name="twitter:title"]',
            'h1'
        ]
        for selector in title_selectors:
            element = soup.select_one(selector)
            if element:
                # For meta tags, the title is in the 'content' attribute.
                title_text = element.get('content', '').strip() or element.get_text(strip=True)
                if len(title_text) > 5: # A reasonable length for a title.
                    return title_text

        # If no suitable title is found, use the last part of the URL as a fallback.
        return url.split('/')[-1] or urlparse(url).netloc

    def _extract_text_from_html(self, html_content: str) -> str:
        """Extracts clean, readable text from raw HTML content."""
        soup = BeautifulSoup(html_content, 'html.parser')

        # Selectors for common non-content elements to remove.
        unwanted_selectors = [
            'script', 'style', 'nav', 'footer', 'header', 'aside', 'form',
            '[class*="cookie"]', '[class*="banner"]', '[id*="ad"]',
            '[aria-hidden="true"]'
        ]
        for selector in unwanted_selectors:
            for element in soup.select(selector):
                element.decompose() # Remove the element from the parse tree.

        # Get the remaining text and clean up whitespace for better readability.
        text = soup.get_text(separator='\n', strip=True)
        return text


    def fetch_url_content(self, url: str) -> Optional[Dict[str, str]]:
        """
        Fetches and extracts text content from a single URL.

        Returns:
            A dictionary with URL, title, content, and error, or None if validation fails.
        """
        if not self._is_valid_url(url):
            return None

        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status() # Raise an exception for HTTP errors.

            content_type = response.headers.get('content-type', '').lower()
            if 'text/html' not in content_type:
                logger.warning(f"Skipping non-HTML content type '{content_type}' for URL: {url}")
                return None

            soup = BeautifulSoup(response.text, 'html.parser')
            title = self._extract_title(soup, url)
            text_content = self._extract_text_from_html(response.text)

            # Truncate content to the specified maximum length.
            if len(text_content) > self.max_content_length:
                text_content = text_content[:self.max_content_length] + "...\n[Content Truncated]"

            return {'url': url, 'title': title, 'content': text_content, 'error': None}

        except requests.RequestException as e:
            logger.error(f"Request failed for {url}: {e}")
            return {'url': url, 'title': url, 'content': '', 'error': str(e)}
        except Exception as e:
            logger.error(f"An unexpected error occurred for {url}: {e}")
            return {'url': url, 'title': url, 'content': '', 'error': str(e)}

    def process_chat_input(self, chat_input: str) -> str:
        """
        Processes a chat input, finds all URLs, fetches their content,
        and returns a single string of augmented context.
        """
        urls = self.extract_urls(chat_input)
        if not urls:
            return chat_input # Return original input if no URLs are found.

        logger.info(f"Found {len(urls)} URL(s): {urls}")
        fetched_content = [self.fetch_url_content(url) for url in urls]

        # Build the final augmented context string.
        context_parts = [
            "Original User Input:",
            f'"{chat_input}"',
            "\n" + "="*25 + "\n",
            "Augmented Context from URLs:"
        ]

        for content in fetched_content:
            if not content:
                continue
            context_parts.append("\n" + "-"*10)
            if content['error']:
                context_parts.append(f"Source URL: {content['url']}\n[Error: Could not fetch content - {content['error']}]")
            else:
                context_parts.extend([
                    f"Source URL: {content['url']}",
                    f"Page Title: {content['title']}",
                    "\n[START CONTENT]",
                    content['content'],
                    "[END CONTENT]"
                ])
        return "\n".join(context_parts)
