"""Unit tests for bot-verification challenge detection."""

from app.utils.bot_challenge import looks_like_bot_challenge

WALMART_CHALLENGE = (
    "Robot or human? Activate and hold the button to confirm that you're "
    "human. Thank You!"
)

CLOUDFLARE_CHALLENGE = (
    "Just a moment... Enable JavaScript and cookies to continue. "
    "www.example.com needs to review the security of your connection before "
    "proceeding."
)

PERIMETERX_CHALLENGE = (
    "Please verify you are a human. Access to this page has been denied "
    "because we believe you are using automation tools to browse the website."
)

FEDERAL_REGISTER_CHALLENGE = (
    "Request Access. Due to aggressive automated scraping of "
    "FederalRegister.gov and eCFR.gov, programmatic access to these sites is "
    "limited to access to our extensive developer APIs. If you are a human "
    "user receiving this message, we can add your IP address to a set of IPs "
    "that can access FederalRegister.gov & eCFR.gov; complete the CAPTCHA "
    "(bot test) below and click \"Request Access\". This process will be "
    "necessary for each IP address you wish to access the site from, "
    "requests are valid for approximately one quarter (three months) after "
    "which the process may need to be repeated."
)


def test_detects_walmart_challenge():
    assert looks_like_bot_challenge(WALMART_CHALLENGE) is True


def test_detects_cloudflare_challenge():
    assert looks_like_bot_challenge(CLOUDFLARE_CHALLENGE) is True


def test_detects_perimeterx_challenge():
    assert looks_like_bot_challenge(PERIMETERX_CHALLENGE) is True


def test_detects_federal_register_request_access():
    assert looks_like_bot_challenge(FEDERAL_REGISTER_CHALLENGE) is True


def test_normal_page_text_passes():
    assert looks_like_bot_challenge(
        "USDA General Terms and Conditions for Federal Awards, effective "
        "December 2025. Recipients must comply with 2 CFR 200."
    ) is False


def test_long_article_about_captchas_passes():
    # A real article that *discusses* bot protection must not be flagged;
    # the length gate keeps marker phrases in long prose from matching.
    article = (
        "This article explains how sites verify you are human using "
        "captchas and challenge pages. " + "More detail follows. " * 300
    )
    assert len(article) > 4000
    assert looks_like_bot_challenge(article) is False


def test_empty_and_none_pass():
    assert looks_like_bot_challenge("") is False
    assert looks_like_bot_challenge(None) is False
    assert looks_like_bot_challenge("   ") is False
