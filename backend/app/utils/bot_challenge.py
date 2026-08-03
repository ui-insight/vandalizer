"""Detect bot-verification challenge pages served in place of real content.

Sites behind Cloudflare, PerimeterX, Akamai, Imperva, etc. respond to
automated visitors with a short interstitial ("Robot or human?",
"Verify you are human", …) instead of the requested page. Crawlers must not
present that text as page content — downstream AI steps would analyze junk.

Detection is deliberately conservative: a page only counts as a challenge
when it is *short* AND contains a known challenge phrase. Real articles that
merely discuss captchas or bot protection are far longer than an
interstitial, so the length gate keeps them out.
"""

# Challenge interstitials are tiny — a few sentences plus a button. Anything
# longer is assumed to be a real page even if a marker phrase appears in it.
_MAX_CHALLENGE_TEXT_CHARS = 4000

# Lowercase phrases as they appear in the *extracted text* of known
# challenge pages (not HTML markup).
_CHALLENGE_MARKERS = (
    "robot or human",                            # Walmart
    "are you a robot",
    "are you a human",
    "verify you are human",                      # Cloudflare Turnstile
    "verifying you are human",
    "verify that you are not a robot",
    "checking your browser before accessing",    # Cloudflare (legacy)
    "enable javascript and cookies to continue", # Cloudflare "Just a moment…"
    "attention required! | cloudflare",
    "please complete the security check",
    "pardon our interruption",                   # Distil/Imperva
    "access to this page has been denied",       # PerimeterX
    "press & hold to confirm",                   # PerimeterX
    "press and hold to confirm",
    "request unsuccessful. incapsula incident",  # Imperva/Incapsula
    "unusual traffic from your computer network",  # Google sorry page
    "ddos protection by",
    "due to aggressive automated scraping",      # FederalRegister.gov / eCFR.gov "Request Access"
    "captcha (bot test)",
)


def looks_like_bot_challenge(text: str | None) -> bool:
    """True when extracted page text is a bot-verification interstitial."""
    if not text:
        return False
    stripped = text.strip()
    if not stripped or len(stripped) > _MAX_CHALLENGE_TEXT_CHARS:
        return False
    lowered = stripped.lower()
    return any(marker in lowered for marker in _CHALLENGE_MARKERS)
