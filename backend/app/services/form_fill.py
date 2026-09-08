"""Form Filler support: checking a fill against its inputs, attributing each
value to a document and page, and reading/writing real PDF form fields.

Three concerns, kept together because they share one data shape — the
per-field ``fill_report`` entry that the workflow UI renders as a table:

* :func:`resolve_fill` — for each value the model returned, decide whether it
  actually appears in the input (verbatim, or as the same number/date), and if
  so which source it came from and on which page. A value that appears nowhere
  in the input is the Form Filler's hallucination signal, exactly as an
  unlocated quote is for extraction (see ``extraction_sources``).
* :func:`pdf_form_fields` / :func:`fill_pdf_form` — enumerate and fill the
  AcroForm widgets of a fillable PDF with PyMuPDF. Real forms name their
  fields things like ``f1_01[0]``, so each field is reported with the label
  text printed next to it, which is what the model needs to map values.
* :func:`load_form_filler_assets` — the one DB-touching helper, used by the
  Celery task-data loaders to attach document metadata and the template PDF
  bytes to a Form Filler task before the engine runs.

Pure string/offset logic apart from that last function; no LLM access.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

from app.services.extraction_sources import (
    _DATE_IN_TEXT_RE,
    _NUMBER_IN_TEXT_RE,
    _as_date,
    _number_with_pct,
    normalize_with_map,
    page_marker_for_offset,
)

logger = logging.getLogger(__name__)

# Characters of surrounding text kept on each side of a located value so the
# report can show the passage it came from.
_QUOTE_CONTEXT_CHARS = 60

# Field types that hold a value we can write. Everything else (push buttons,
# signature fields) is reported but never filled.
PDF_FIELD_TEXT = "text"
PDF_FIELD_CHECKBOX = "checkbox"
PDF_FIELD_RADIO = "radiobutton"
PDF_FIELD_COMBOBOX = "combobox"
PDF_FIELD_LISTBOX = "listbox"
FILLABLE_PDF_FIELD_TYPES = frozenset({
    PDF_FIELD_TEXT, PDF_FIELD_CHECKBOX, PDF_FIELD_RADIO, PDF_FIELD_COMBOBOX, PDF_FIELD_LISTBOX,
})

_TRUE_WORDS = frozenset({"true", "yes", "y", "x", "on", "checked", "1"})
_FALSE_WORDS = frozenset({"false", "no", "n", "off", "unchecked", "0", ""})


# ---------------------------------------------------------------------------
# Value support and attribution
# ---------------------------------------------------------------------------


def _squash(text: str) -> str:
    return " ".join(text.split())


# What the model says when it has nothing, written as a value instead of
# null: "Not provided in context", "The document does not mention this",
# "N/A", "unknown". Rendered as-is these read as filled-in answers — a form
# with failure notes baked into it, marked Completed with no warning (support
# ticket). Anything matching here is a missing value: it gets the missing
# marker and the field is listed on the step's warning. Bare sentinels are
# the same set extraction treats as not-found (extraction_sources
# ._NOT_FOUND_VARIANTS); the phrase forms add the "in the context" tail and
# the "the context does not …" sentence. A value that merely *starts* with
# one of these words ("None of the above", "Unknown Author", "Not-for-profit")
# does not match: the tail must be a locating clause or nothing at all.
_FORM_NULLISH_HEAD = (
    r"(?:n/?a|n\.a\.|none|null|nil|unknown|unavailable|missing|empty|blank|tbd|"
    r"to be determined|-{1,3}|—|"
    r"no (?:data|value|information|info|entry)(?: (?:available|provided|given|found|supplied))?|"
    r"not (?:provided|specified|available|found|stated|mentioned|given|present|"
    r"applicable|listed|included|supplied|indicated|determined|"
    r"in (?:the )?(?:context|document|input|source|text)))"
)
_FORM_NULLISH_SENTENCE = (
    r"(?:the )?(?:context|document|input|source|text|information)s? "
    r"(?:does not|doesn't|did not|didn't|do not|don't) "
    r"(?:contain|mention|state|provide|specify|include|list|give|say|indicate).*"
)
_FORM_NULLISH_RE = re.compile(
    r"^\W*(?:" + _FORM_NULLISH_SENTENCE + r"|" + _FORM_NULLISH_HEAD +
    r"(?:\s*:\s*.*|\s+[\-–—]\s+.*|\s+(?:in|from|within|by|for|per|on)\b.*)?)\W*$",
    re.IGNORECASE | re.DOTALL,
)
# Phrases in freehand output (a template with no {{markers}}) that mean a
# blank went unfilled. Counted, not parsed: the model wrote the form itself,
# so the count feeds the warning and nothing else.
_FORM_FREEFORM_UNFILLED_RE = re.compile(
    r"\bnot (?:provided|specified|available|found|stated|mentioned|given|supplied)"
    r"(?:\s+in\s+(?:the\s+)?(?:context|document|input|source|text))?\b|"
    r"\bno information (?:provided|available|given)\b|"
    r"\b(?:the )?(?:context|document|input) (?:does not|doesn't) (?:contain|mention|state|provide|specify)\b",
    re.IGNORECASE,
)


def form_value_is_missing(value) -> bool:
    """True for null, blank, and prose that says there is no value."""
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    return not stripped or bool(_FORM_NULLISH_RE.match(stripped))


# Back-compat alias for callers/tests written against the first name.
value_is_missing = form_value_is_missing


def _value_text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value.strip()
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return str(value)


def _find_bounded(haystack: str, needle: str) -> Optional[int]:
    """First occurrence of *needle* that is not glued to a neighbouring word or
    number: "12" must not match inside "2012", "Ada" not inside "Adam"."""
    if not needle:
        return None
    start = 0
    while True:
        idx = haystack.find(needle, start)
        if idx == -1:
            return None
        end = idx + len(needle)
        before = haystack[idx - 1] if idx > 0 else " "
        after = haystack[end] if end < len(haystack) else " "
        glued_before = needle[0].isalnum() and before.isalnum()
        glued_after = needle[-1].isalnum() and after.isalnum()
        if not glued_before and not glued_after:
            return idx
        start = idx + 1


def find_value_offset(text: str, value: str) -> tuple[Optional[int], Optional[str]]:
    """Locate *value* in *text*; return (char offset, method) or (None, None).

    Tries, in order: the same string (with case, whitespace and unicode
    folding), then the same number (respecting a percent sign) or the same
    calendar date written any common way.
    """
    if not text or not value:
        return None, None

    normalized = normalize_with_map(text)
    norm_text, index_map = normalized
    norm_value, _ = normalize_with_map(value)

    # normalize_with_map folds case, whitespace runs and unicode variants
    # (quotes, dashes, NBSP, ligatures), so "verbatim" here means the same
    # characters up to those folds — the differences a PDF text layer
    # introduces, not ones a model does.
    idx = _find_bounded(norm_text, norm_value)
    if idx is not None:
        return index_map[idx], "verbatim"

    number = _number_with_pct(value)
    if number is not None:
        want, want_pct = number
        for m in _NUMBER_IN_TEXT_RE.finditer(text):
            token = m.group(0)
            end = m.end()
            has_pct = end < len(text) and text[end:end + 1] == "%"
            got = _number_with_pct(token + ("%" if has_pct else ""))
            if got is None:
                continue
            if got[0] == want and got[1] == want_pct:
                # Don't match a digit run inside a longer number ("12" in "2012").
                before = text[m.start() - 1] if m.start() > 0 else " "
                if before.isdigit() or before == ".":
                    continue
                return m.start(), "same_number"

    wanted_date = _as_date(value)
    if wanted_date is not None:
        for m in _DATE_IN_TEXT_RE.finditer(text):
            if _as_date(m.group(0)) == wanted_date:
                return m.start(), "same_date"

    return None, None


def _quote_around(text: str, offset: int, length: int) -> str:
    start = max(0, offset - _QUOTE_CONTEXT_CHARS)
    end = min(len(text), offset + length + _QUOTE_CONTEXT_CHARS)
    snippet = _squash(text[start:end])
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet


def resolve_fill(values: dict, sources: list[dict], *, field_order: list[str] | None = None) -> list[dict]:
    """Check every filled value against the inputs and say where it came from.

    *sources* is the ordered list of inputs the model saw, each
    ``{"kind", "title", "text", "uuid"?, "text_markers"?}`` — for a workflow
    document ``text_markers`` gives page boundaries; a previous step's output
    has neither uuid nor pages.

    Returns one entry per field, in *field_order* (default: dict order)::

        {"name", "value", "status": "supported" | "unsupported" | "missing",
         "method", "document_uuid", "document_title", "page",
         "page_approximate", "quote"}

    ``unsupported`` means the value appears in none of the inputs — the model
    reformatted it or made it up; either way it needs a human eye before the
    form is used.
    """
    order = field_order if field_order is not None else list(values.keys())
    report: list[dict] = []
    for name in order:
        value = values.get(name)
        entry: dict[str, Any] = {"name": name, "value": value}
        if value_is_missing(value):
            entry["status"] = "missing"
            report.append(entry)
            continue
        if isinstance(value, bool):
            # A checkbox state is a decision, not a copied string; there is no
            # passage to find for it. Reported as supported without a source
            # rather than flagged, so a form full of ticks does not read as a
            # form full of inventions.
            entry.update({"status": "supported", "method": "boolean"})
            report.append(entry)
            continue
        text_value = _value_text(value)
        located = False
        for src in sources:
            src_text = src.get("text") or ""
            offset, method = find_value_offset(src_text, text_value)
            if offset is None:
                continue
            # Legacy interpolated markers stored before the `approximate` flag
            # existed would otherwise cite confident exact pages in fill reports.
            from app.services.page_locator import with_marker_provenance

            marker = page_marker_for_offset(
                offset, with_marker_provenance(src.get("text_markers")) or [],
            )
            entry.update({
                "status": "supported",
                "method": method,
                "document_uuid": src.get("uuid"),
                "document_title": src.get("title"),
                "page": marker.get("value") if marker else None,
                "quote": _quote_around(src_text, offset, len(text_value)),
            })
            if marker and marker.get("approximate"):
                entry["page_approximate"] = True
            located = True
            break
        if not located:
            entry["status"] = "unsupported"
        report.append(entry)
    return report


def describe_fill_report(report: list[dict], *, missing_token: str | None) -> list[str]:
    """Warning sentences for a report: unfilled fields, then unsupported values."""
    warnings: list[str] = []
    missing = [e["name"] for e in report if e.get("status") == "missing"]
    unsupported = [e for e in report if e.get("status") == "unsupported"]
    if missing:
        n = len(missing)
        how = (
            f"marked {missing_token} in the form — fill in or remove before using it"
            if missing_token else "left blank in the form — fill in before using it"
        )
        warnings.append(
            f"{n} field{'s' if n != 1 else ''} not found in the input and {how}: "
            + ", ".join(missing)
        )
    if unsupported:
        n = len(unsupported)
        listed = ", ".join(f"{e['name']} ({_value_text(e.get('value'))!r})" for e in unsupported)
        warnings.append(
            f"{n} value{'s' if n != 1 else ''} do{'es' if n == 1 else ''} not appear anywhere in the "
            f"input data and may be invented or reformatted — check before use: {listed}"
        )
    return warnings


# ---------------------------------------------------------------------------
# Fillable PDF forms (PyMuPDF)
# ---------------------------------------------------------------------------


def _open_pdf(pdf_bytes: bytes):
    import fitz  # PyMuPDF

    return fitz, fitz.open(stream=pdf_bytes, filetype="pdf")


def _label_near_widget(page, rect) -> str:
    """Text printed just left of / above a widget — the human label for it."""
    import fitz

    left = fitz.Rect(rect.x0 - 220, rect.y0 - 4, rect.x0 - 1, rect.y1 + 4)
    above = fitz.Rect(rect.x0 - 10, rect.y0 - 18, rect.x1 + 10, rect.y0 - 1)
    parts: list[str] = []
    for clip in (left, above):
        try:
            found = _squash(page.get_text("text", clip=clip) or "")
        except Exception:  # pragma: no cover - defensive around MuPDF
            found = ""
        if found and found not in parts:
            parts.append(found)
    label = " / ".join(parts)
    return label[:120]


def pdf_form_fields(pdf_bytes: bytes) -> list[dict]:
    """Describe a PDF's form fields, first appearance order, one entry per name.

    Each entry: ``{"name", "type", "page", "label"?, "choices"?}``. Radio
    groups (several widgets sharing a name) are one entry whose ``choices``
    are the widgets' on-states. Non-fillable widget types are listed with
    their type so the caller can report them, but carry no ``choices``.
    """
    fitz, doc = _open_pdf(pdf_bytes)
    fields: list[dict] = []
    by_name: dict[str, dict] = {}
    try:
        for page in doc:
            for widget in page.widgets():
                name = (widget.field_name or "").strip()
                if not name:
                    continue
                ftype = (widget.field_type_string or "").lower()
                if name in by_name:
                    if ftype == PDF_FIELD_RADIO:
                        state = widget.on_state()
                        choices = by_name[name].setdefault("choices", [])
                        if state and state not in choices:
                            choices.append(state)
                    continue
                entry: dict[str, Any] = {"name": name, "type": ftype, "page": page.number + 1}
                label = _label_near_widget(page, widget.rect)
                if label:
                    entry["label"] = label
                if ftype in (PDF_FIELD_COMBOBOX, PDF_FIELD_LISTBOX):
                    entry["choices"] = [str(c) for c in (widget.choice_values or [])]
                elif ftype == PDF_FIELD_RADIO:
                    state = widget.on_state()
                    entry["choices"] = [state] if state else []
                by_name[name] = entry
                fields.append(entry)
    finally:
        doc.close()
    return fields


def _as_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    word = str(value).strip().lower()
    if word in _TRUE_WORDS:
        return True
    if word in _FALSE_WORDS:
        return False
    return None


def _pick_choice(value: Any, choices: list[str]) -> Optional[str]:
    wanted = _squash(str(value)).lower()
    for choice in choices:
        if _squash(choice).lower() == wanted:
            return choice
    return None


def fill_pdf_form(pdf_bytes: bytes, values: dict) -> tuple[bytes, list[str], list[tuple[str, str]]]:
    """Write *values* into the PDF's form fields.

    Returns ``(filled_pdf_bytes, applied_field_names, skipped)`` where
    *skipped* lists ``(name, reason)`` for values that could not be written —
    a choice not among the field's options, an unrecognised checkbox state, a
    field type with no value slot. A field whose value is missing is left as
    it was, never written with a placeholder token: this is someone's real
    form.
    """
    fitz, doc = _open_pdf(pdf_bytes)
    applied: list[str] = []
    skipped: list[tuple[str, str]] = []
    seen_skip: set[str] = set()

    def _skip(name: str, reason: str) -> None:
        if name not in seen_skip:
            seen_skip.add(name)
            skipped.append((name, reason))

    try:
        for page in doc:
            for widget in page.widgets():
                name = (widget.field_name or "").strip()
                if not name or name not in values:
                    continue
                value = values[name]
                if value_is_missing(value) and not isinstance(value, bool):
                    continue
                ftype = (widget.field_type_string or "").lower()
                try:
                    if ftype == PDF_FIELD_TEXT:
                        widget.field_value = _value_text(value) if not isinstance(value, str) else value
                        widget.update()
                    elif ftype == PDF_FIELD_CHECKBOX:
                        state = _as_bool(value)
                        if state is None:
                            _skip(name, f"checkbox needs true/false, got {str(value)!r}")
                            continue
                        widget.field_value = widget.on_state() if state else "Off"
                        widget.update()
                    elif ftype == PDF_FIELD_RADIO:
                        on_state = widget.on_state() or ""
                        selected = _squash(str(value)).lower() == _squash(on_state).lower()
                        if selected:
                            widget.field_value = on_state
                            widget.update()
                        else:
                            # Only mark skipped if no widget of this group matched.
                            continue
                    elif ftype in (PDF_FIELD_COMBOBOX, PDF_FIELD_LISTBOX):
                        choices = [str(c) for c in (widget.choice_values or [])]
                        chosen = _pick_choice(value, choices)
                        if chosen is None:
                            _skip(name, f"{str(value)!r} is not one of the field's options")
                            continue
                        widget.field_value = chosen
                        widget.update()
                    else:
                        _skip(name, f"{ftype or 'unknown'} fields cannot hold a value")
                        continue
                except Exception as e:  # MuPDF raises plain Exception/RuntimeError
                    _skip(name, f"could not write value: {e}")
                    continue
                if name not in applied:
                    applied.append(name)
        # Radio groups: a value that matched no button in the group.
        radio_names = {
            (w.field_name or "").strip()
            for page in doc for w in page.widgets()
            if (w.field_type_string or "").lower() == PDF_FIELD_RADIO
        }
        for name in radio_names:
            if name in values and not value_is_missing(values[name]) and name not in applied:
                _skip(name, f"{str(values[name])!r} is not one of the group's options")
        return doc.tobytes(deflate=True), applied, skipped
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# Task-data preload (sync DB, called from Celery task builders)
# ---------------------------------------------------------------------------

_DOC_META_FIELDS = ("uuid", "title", "text_markers")


#: Step tasks whose node needs per-document metadata hydrated alongside
#: ``doc_texts``. Form Filler attributes each filled value to a document and
#: page; Extraction resolves each field's supporting quote the same way.
#: Anything else would carry the markers unread.
DOC_META_TASKS = ("FormFiller", "Extraction")


def document_meta(doc: dict) -> dict:
    """The per-document metadata a Form Filler or Extraction task carries for
    attribution."""
    return {
        "uuid": doc.get("uuid"),
        "title": doc.get("title") or doc.get("uuid") or "Document",
        "text_markers": doc.get("text_markers") or [],
    }


def load_form_filler_assets(db, task_data: dict, *, upload_dir: str) -> None:
    """Attach the template PDF to a Form Filler task's data, in place.

    Sets ``template_pdf_b64`` and ``template_document_title`` when
    ``template_source == "pdf"`` and the referenced document is a PDF on disk;
    otherwise sets ``template_load_error`` with the reason so the node can
    fail the step with a message instead of filling nothing.
    """
    if (task_data.get("template_source") or "text") != "pdf":
        return
    doc_uuid = (task_data.get("template_document_uuid") or "").strip()
    if not doc_uuid:
        task_data["template_load_error"] = (
            "Form Filler is set to fill a PDF form but no template document is selected."
        )
        return
    doc = db.smart_document.find_one({"uuid": doc_uuid})
    if not doc:
        task_data["template_load_error"] = (
            f"The template document ({doc_uuid}) no longer exists."
        )
        return
    title = doc.get("title") or doc_uuid
    if (doc.get("extension") or "").lower() != "pdf":
        task_data["template_load_error"] = (
            f"The template document '{title}' is not a PDF (.{doc.get('extension') or '?'})."
        )
        return
    rel = doc.get("path") or ""
    path = Path(rel) if Path(rel).is_absolute() else Path(upload_dir) / rel
    if not rel or not path.exists():
        task_data["template_load_error"] = (
            f"The file for template document '{title}' is missing on the server."
        )
        return
    try:
        pdf_bytes = path.read_bytes()
    except OSError as e:
        task_data["template_load_error"] = f"Could not read template document '{title}': {e}"
        return
    task_data["template_pdf_b64"] = base64.b64encode(pdf_bytes).decode("ascii")
    task_data["template_document_title"] = title


_FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9_\-. ]+")


def filled_pdf_filename(template_title: str | None) -> str:
    stem = (template_title or "form").rsplit(".", 1)[0] if template_title else "form"
    stem = _FILENAME_SAFE_RE.sub("_", stem).strip(" _.") or "form"
    return f"{stem}-filled.pdf"
