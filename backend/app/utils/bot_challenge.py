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


# ---------------------------------------------------------------------------
# Boilerplate-only pages
# ---------------------------------------------------------------------------
# A JavaScript-rendered site (grants.gov is the case that bit us) answers a
# scraper with HTTP 200 and a shell containing only the site chrome — the .gov
# banner, nav, footer, a session-timeout dialog. It is not a bot challenge and
# it is not empty, so both existing gates pass it and the chrome gets embedded
# as if it were content. Retrieval then serves padlock trivia, and auto
# question generation writes test questions about session timeouts.

_MAX_CHROME_TEXT_CHARS = 4000

# Chrome phrases, grouped by the thing they belong to. Grouping is the whole
# mechanism: counting individual phrases cannot distinguish "this page has the
# .gov banner" from "this page is nothing but furniture", because the banner
# alone supplies several phrases and every real .gov page carries it. Two
# phrases from one family is one signal; two *families* is a page assembled
# from parts that only co-occur on an empty shell.
#
# It also removes an accidental double-count: "locked padlock icon" is a
# substring of "a lock ( lock locked padlock icon )", so a single lock sentence
# used to satisfy a two-marker threshold by itself.
_CHROME_MARKER_FAMILIES: dict[str, tuple[str, ...]] = {
    # The standard USWDS banner. Present on every .gov page, real or not.
    "gov_banner": (
        "an official website of the united states government",
        "here's how you know",
        "a lock ( lock locked padlock icon )",
        "locked padlock icon",
        "share sensitive information only on official, secure websites",
    ),
    # A timeout dialog rendered into the shell before any content arrives.
    "session_dialog": (
        "your session will expire in",
        "to continue working, click on the",
    ),
    # The page telling us outright that its content is client-side.
    "js_required": (
        "enable javascript to use this site",
        "this site requires javascript",
    ),
}

# Flat view, kept for callers that just want to know the phrases.
_CHROME_MARKERS = tuple(
    marker for family in _CHROME_MARKER_FAMILIES.values() for marker in family
)

# Distinct families, not distinct phrases. See the note above.
_MIN_CHROME_FAMILIES = 2


def looks_like_boilerplate_only(text: str | None) -> bool:
    """True when extracted page text is site chrome with no real content.

    Conservative in the same way as :func:`looks_like_bot_challenge`: the page
    must be *short* AND draw chrome from more than one family. The length gate
    alone is not enough to separate "chrome-only" from "short" — a real policy
    notice of a few hundred words carries the .gov banner too, and rejecting it
    means its content is never indexed, which is worse than the padlock trivia
    this gate exists to keep out.
    """
    if not text:
        return False
    stripped = text.strip()
    if not stripped or len(stripped) > _MAX_CHROME_TEXT_CHARS:
        return False
    lowered = stripped.lower()
    families = sum(
        1
        for markers in _CHROME_MARKER_FAMILIES.values()
        if any(marker in lowered for marker in markers)
    )
    return families >= _MIN_CHROME_FAMILIES
