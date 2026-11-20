"""Native Page navigation; authored scripts and app access remain blocked."""
import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup


PAGE_LINK_SANDBOX = "allow-popups allow-popups-to-escape-sandbox"


def prepare_page_links(html: str, csp: str) -> tuple[str, str]:
    """Normalize links at save and delivery, including older immutable revisions.

    Only a clicked, allowlisted anchor can open another context. Its destination
    does not inherit the Page sandbox, and cannot access the opener or referrer.
    Keep other sandbox restrictions (including any trusted print permissions).
    """
    def permissions(match: re.Match[str]) -> str:
        tokens = match[0].split()
        return " ".join(dict.fromkeys([*tokens, *PAGE_LINK_SANDBOX.split()]))

    csp = re.sub(r"\bsandbox\b[^;]*", permissions, csp)
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.find_all("a"):
        href = link.get("href", "")
        # Never retain authored targets, opener relationships or referrer policy.
        for attribute in ("target", "rel", "referrerpolicy"):
            link.attrs.pop(attribute, None)
        if not isinstance(href, str) or not href:
            continue
        if href.startswith("#"):
            continue
        try:
            scheme = urlsplit(href).scheme.lower()
        except ValueError:
            scheme = ""
        if scheme in {"https", "http", "mailto"}:
            link["target"] = "_blank"
            link["rel"] = "noopener noreferrer"
        else:
            link.attrs.pop("href", None)
    for meta in soup.find_all("meta"):
        if str(meta.get("http-equiv", "")).lower() == "content-security-policy":
            meta["content"] = csp
    return str(soup), csp
