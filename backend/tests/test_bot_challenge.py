"""Unit tests for bot-verification challenge detection."""

from app.utils.bot_challenge import (
    looks_like_boilerplate_only,
    looks_like_bot_challenge,
)

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


# ---------------------------------------------------------------------------
# Boilerplate-only pages (JS-rendered sites that serve just their shell)
# ---------------------------------------------------------------------------

# What grants.gov actually returned for the 2 CFR 200 KB's policy source:
# HTTP 200, no bot challenge, but the body is only site chrome. It was
# embedded as content and the KB answered questions about padlock icons and
# session timeouts.
GRANTS_GOV_SHELL = (
    "An official website of the United States government Here's how you know "
    "Official websites use .gov A .gov website belongs to an official "
    "government organization in the United States. Secure .gov websites use "
    "HTTPS A lock ( Lock Locked padlock icon ) or https:// means you've "
    "safely connected to the .gov website. Share sensitive information only "
    "on official, secure websites. Menu Search Site Content Help Register "
    "Login Return to top Connect with Us Blog Alerts RSS Accessibility "
    "Privacy Site Map USA.gov Report Fraud "
    'Your session will expire in 3 minutes. To continue working, click on '
    'the "OK" button below. No'
)


def test_detects_grants_gov_chrome_only_shell():
    assert looks_like_boilerplate_only(GRANTS_GOV_SHELL) is True


def test_chrome_only_shell_is_not_a_bot_challenge():
    # It must be caught by the new gate specifically — the bot-challenge gate
    # has no reason to fire, which is why this page slipped through before.
    assert looks_like_bot_challenge(GRANTS_GOV_SHELL) is False


def test_real_gov_page_with_banner_passes():
    # Real .gov pages carry the same banner; length is what separates them.
    page = (
        "An official website of the United States government Here's how you "
        "know. Secure .gov websites use HTTPS. "
    ) + (
        "Equipment means tangible personal property having a useful life of "
        "more than one year and a per-unit acquisition cost that equals or "
        "exceeds the lesser of the capitalization level established by the "
        "recipient or $10,000. " * 40
    )
    assert looks_like_boilerplate_only(page) is False


def test_single_chrome_marker_is_not_enough():
    # One marker on a short page is not a confident signal.
    assert looks_like_boilerplate_only(
        "An official website of the United States government. "
        "The cost of alcoholic beverages is unallowable."
    ) is False


def test_short_real_content_passes():
    assert looks_like_boilerplate_only(
        "The cost of alcoholic beverages is unallowable."
    ) is False


def test_empty_boilerplate_input():
    assert looks_like_boilerplate_only("") is False
    assert looks_like_boilerplate_only(None) is False


# What a plain fetch of an ecfr.gov content page returns: the search-help
# panel and nothing else. Verbatim from a seeded 2 CFR 200 subpart source,
# which had been indexed as exactly this one paragraph.
ECFR_SHELL = (
    "Navigate by entering citations or phrases (eg: 1 CFR 1.1 49 CFR 172.101 "
    "Organization and Purpose 1/1.1 Regulation Y FAR). Choosing an item from "
    "citations and headings will bring you directly to the content. Choosing "
    "an item from full text search results will bring you to those results. "
    "Pressing enter in the search box will also bring you to search results. "
    "Background and more details are available in the Search & Navigation guide."
)


def test_detects_ecfr_search_help_shell():
    # No .gov banner, so the two-family rule never fired on it; the help
    # panel alone, on a short page with no section text, is the shell.
    assert looks_like_boilerplate_only(ECFR_SHELL) is True
    assert looks_like_bot_challenge(ECFR_SHELL) is False


def test_ecfr_page_with_regulation_text_passes():
    page = ECFR_SHELL + (
        " § 200.414 Indirect (F&A) costs. (f) In addition to the procedures "
        "outlined in the appendices in paragraph (e) of this section, any "
        "non-Federal entity that does not have a current negotiated rate may "
        "elect to charge a de minimis rate of 15% of modified total direct costs."
    )
    assert looks_like_boilerplate_only(page) is False


# ---------------------------------------------------------------------------
# Marker families: a real page carrying the .gov banner must survive
# ---------------------------------------------------------------------------

# The standard USWDS banner, verbatim. Every .gov page has it — real or shell.
GOV_BANNER = (
    "An official website of the United States government Here's how you know "
    "Official websites use .gov A lock ( Lock Locked padlock icon ) or https:// "
    "means you've safely connected to the .gov website. Share sensitive "
    "information only on official, secure websites."
)


def test_a_short_real_page_carrying_the_full_banner_is_kept():
    """Counting phrases rather than families rejected real content.

    The banner alone supplies five of the marker phrases, so any threshold
    counting phrases is met before the page's own text is considered. A policy
    notice of a few hundred words is short *and* carries the banner, and
    rejecting it means `_ingest_url_source` marks the source an error and its
    content is never indexed — worse than the padlock trivia the gate exists
    to exclude.
    """
    page = GOV_BANNER + " " + (
        "The de minimis indirect cost rate is 15 percent of modified total "
        "direct costs. Recipients must retain records for three years after "
        "submission of the final expenditure report. " * 6
    )
    assert len(page) < 4000, "fixture must stay inside the length gate to be meaningful"
    assert looks_like_boilerplate_only(page) is False


def test_one_lock_sentence_does_not_count_twice():
    """"locked padlock icon" is a substring of "a lock ( lock locked padlock
    icon )", so a single sentence used to satisfy a two-marker threshold on its
    own."""
    assert looks_like_boilerplate_only(
        "A lock ( Lock Locked padlock icon ) means you are secure. "
        "The de minimis rate is 15 percent."
    ) is False


def test_the_whole_banner_alone_is_still_only_one_signal():
    assert looks_like_boilerplate_only(GOV_BANNER) is False


def test_banner_plus_a_session_dialog_is_a_shell():
    """Two families is the signal: a timeout dialog rendered before any content
    only co-occurs with the banner on an empty shell."""
    assert looks_like_boilerplate_only(
        GOV_BANNER + " Your session will expire in 5 minutes. "
        "To continue working, click on the button below."
    ) is True


def test_banner_plus_a_javascript_notice_is_a_shell():
    assert looks_like_boilerplate_only(
        GOV_BANNER + " This site requires JavaScript. "
        "Please enable JavaScript to use this site."
    ) is True
