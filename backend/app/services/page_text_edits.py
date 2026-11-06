"""Apply text the owner typed into a Page ("Edit text") to its saved HTML.

Support ticket: fixing one word, heading, date or dollar amount on a saved
Page meant a chat round trip (Request changes) or editing ~160 lines of raw
HTML (Edit HTML). In Edit text mode the embed script makes each innermost
text block (heading, paragraph, list item, table cell) editable as plain
text. On Save it reports, for each changed block, the tag, the text it had,
which occurrence of that tag-and-text it is, and the new text.

The browser's DOM is not the saved HTML: the embed script wraps tables and
the browser adds <tbody>, so positions don't line up. Blocks are found again
by tag, original text and occurrence instead, and an edit whose original is
no longer there is refused rather than guessed at.

Only the changed span is replaced. When it falls inside one text node, the
block keeps its bold, links and other inline formatting. When it spans
several, the block becomes plain text and the result says so.
"""

from __future__ import annotations

from dataclasses import dataclass

from bs4 import BeautifulSoup, NavigableString, Tag
from fastapi import HTTPException

EDITABLE_TAGS = frozenset({
    "td", "th", "li", "p", "h1", "h2", "h3", "h4", "h5", "h6", "dt", "dd",
    "figcaption", "caption", "blockquote", "pre",
})
MAX_EDITS = 200
MAX_TEXT = 20_000


@dataclass(frozen=True)
class TextEdit:
    tag: str
    index: int
    original: str
    text: str


def _text_nodes(element: Tag) -> list[NavigableString]:
    return [node for node in element.descendants if isinstance(node, NavigableString)
            and node.__class__ is NavigableString]


def _replace_span(element: Tag, original: str, new: str) -> bool:
    """Replace the changed span in place. Returns False when formatting was dropped."""
    prefix = 0
    limit = min(len(original), len(new))
    while prefix < limit and original[prefix] == new[prefix]:
        prefix += 1
    suffix = 0
    while (suffix < limit - prefix and original[len(original) - 1 - suffix] == new[len(new) - 1 - suffix]):
        suffix += 1
    start, end = prefix, len(original) - suffix
    replacement = new[prefix:len(new) - suffix]
    offset = 0
    for node in _text_nodes(element):
        node_start, node_end = offset, offset + len(node)
        offset = node_end
        # The change sits inside this one text node (an insertion at a node
        # boundary goes to the node that ends there).
        if node_start <= start and end <= node_end:
            text = str(node)
            node.replace_with(NavigableString(text[:start - node_start] + replacement + text[end - node_start:]))
            return True
    element.clear()
    element.append(NavigableString(new))
    return False


def apply(html: str, edits: list[TextEdit]) -> tuple[str, list[str]]:
    """The saved HTML with *edits* applied, and notes about blocks that lost formatting."""
    if not edits:
        raise HTTPException(422, "No text was changed.")
    if len(edits) > MAX_EDITS:
        raise HTTPException(422, f"Save at most {MAX_EDITS} changed blocks at a time.")
    soup = BeautifulSoup(html, "html.parser")
    body = soup.body or soup
    # Locate every block before changing any, so one edit can't shift another's match.
    targets: list[tuple[Tag, TextEdit]] = []
    for edit in edits:
        if edit.tag not in EDITABLE_TAGS:
            raise HTTPException(422, f"<{edit.tag}> can't be edited as text. Use Edit HTML.")
        if len(edit.text) > MAX_TEXT or len(edit.original) > MAX_TEXT:
            raise HTTPException(422, "That block is too long to edit as text. Use Edit HTML.")
        matches = [el for el in body.find_all(edit.tag) if el.get_text() == edit.original]
        if edit.index < 0 or edit.index >= len(matches):
            raise HTTPException(409, "Part of the page changed while you were editing. Reload the page and make the change again.")
        targets.append((matches[edit.index], edit))
    notes: list[str] = []
    for element, edit in targets:
        if edit.text == edit.original:
            continue
        if not _replace_span(element, edit.original, edit.text):
            notes.append(f'Formatting inside "{edit.text[:60]}" was removed because the change spanned several styles.')
    result = str(soup)
    if result == html:
        raise HTTPException(422, "No text was changed.")
    return result, notes
