"""Keep claims of document checks within the reply's actual source scope.

Attachment metadata is not a read receipt. Workspace listings, references
inside a workbook, and generated pages are not original reference documents.
This is a narrow check on explicit verification claims, not a content verifier.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    title: str
    extension: str = ""
    uuid: str = ""
    readable: bool = False


_VERBS = r"(?:cross[ -]checked|verified|validated|compared|checked|reviewed)"
_CHECK = re.compile(
    rf"^(?:Additionally,?\s+|Also,?\s+)?(?:"
    rf"(?:I|We)(?:['’](?:ve)|\s+have)?\s+(?:(?:also|now|already|successfully|independently|carefully|fully)\s+)*{_VERBS}"
    rf"|(?:The|This|Your)\s+(?:spreadsheet|workbook|page|report|data|figures|results)\s+"
    rf"(?:has been|have been|was|were|is|are)\s+{_VERBS}"
    rf"|{_VERBS}\s+(?:against|with))\b",
    re.I,
)
_REFERENCE = re.compile(
    r"\b(?:docx?|pdf|word (?:documents?|summaries)|reference (?:documents?|files?|summaries)|"
    r"attached (?:reference )?(?:documents?|files?|summaries)|documents? (?:you )?(?:attached|uploaded))\b",
    re.I,
)
_ATTACHED = re.compile(r"\b(?:attached|uploaded)\b", re.I)
_QUOTED_FILE = re.compile(r'''["“‘']([^"“”‘’'\n]+\.(?:docx?|pdf|xlsx?|csv|txt))["”’']''', re.I)
_BARE_FILE = re.compile(r"\b[\w.-]+\.(?:docx?|pdf|xlsx?|csv|txt)\b", re.I)
_FILE_TYPES = (
    (re.compile(r"\bdocx\b", re.I), {"docx"}),
    (re.compile(r"\bdoc\b|\bword (?:documents?|summaries)\b", re.I), {"doc", "docx"}),
    (re.compile(r"\bpdf\b", re.I), {"pdf"}),
    (re.compile(r"\b(?:spreadsheet|workbook|excel)\b", re.I), {"xls", "xlsx", "csv"}),
)
UNVERIFIED_CHECK = "I couldn’t verify this against the referenced documents."


def _extension(source: Source) -> str:
    return (source.extension or source.title.rsplit(".", 1)[-1]).lower().lstrip(".")


def attachment_sources(documents, files, document_segments, attachment_segments) -> list[Source]:
    """Use the post-compaction segments, not raw text the model never received."""
    labels = {segment.label for segment in [*document_segments, *attachment_segments] if segment.text.strip()}
    return [
        Source(doc.title or doc.uuid, doc.extension or "", doc.uuid,
               bool(doc.raw_text) and f"doc:{doc.title or doc.uuid}" in labels)
        for doc in documents
    ] + [
        Source(att.filename, readable=bool(att.content) and f"file:{att.filename}" in labels)
        for att in files
    ]


def ground_source_checks(answer: str, attached: list[Source], tool_results: list[dict]) -> str:
    """Replace unsupported completed-check sentences before streaming/saving.

    A successful read can supply missing content, but cannot make a workspace
    document an attachment. Discovery and failed reads supply no evidence.
    """
    reads = []
    for result in tool_results:
        content = result.get("content")
        if (result.get("tool_name") == "get_document_text" and isinstance(content, dict)
                and not content.get("error") and isinstance(content.get("text"), str)
                and content["text"].strip()):
            reads.append(Source(content.get("title") or "", content.get("extension") or "",
                                content.get("uuid") or "", True))

    def same_source(a: Source, b: Source) -> bool:
        if a.uuid and b.uuid:
            return a.uuid == b.uuid
        return bool(a.title) and a.title.casefold() == b.title.casefold()

    readable_attachments = [source for source in attached if source.readable or any(same_source(source, r) for r in reads)]
    available = readable_attachments + [r for r in reads if not any(same_source(r, a) for a in readable_attachments)]

    def supported(sentence: str) -> bool:
        plain = re.sub(r"[*`_]", "", sentence).strip()
        plain = re.sub(r"^[-•]\s+", "", plain)
        # "I checked the workbook, but haven't checked the reference docs" is
        # a limitation, not a claim to have read those references.
        plain = re.split(r",?\s+\b(?:but|however)\b", plain, maxsplit=1, flags=re.I)[0]
        if not _CHECK.search(plain):
            return True
        quoted = _QUOTED_FILE.findall(plain)
        names = quoted + _BARE_FILE.findall(_QUOTED_FILE.sub("", plain))
        if not _REFERENCE.search(plain) and not names:
            return True
        sources = readable_attachments if _ATTACHED.search(plain) else available
        if any(not any(name.casefold() == s.title.casefold() for s in sources) for name in names):
            return False
        for pattern, extensions in _FILE_TYPES:
            if pattern.search(plain) and not any(_extension(s) in extensions for s in sources):
                return False
        comparing = bool(re.search(r"cross[ -]checked|\b(?:against|compared|with)\b", plain, re.I))
        if len(names) == 1 and re.search(r"\bsheets?\s+in\b", plain, re.I) and not _REFERENCE.search(plain):
            comparing = False  # Comparing sheets within one workbook needs one source.
        identities = {s.uuid or s.title.casefold() for s in sources}
        return len(identities) >= (2 if comparing else 1)

    paragraphs = []
    for paragraph in answer.split("\n\n"):
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", paragraph)
        checked = [sentence if supported(sentence) else UNVERIFIED_CHECK for sentence in sentences]
        paragraphs.append(" ".join(checked) if checked != sentences else paragraph)
    return "\n\n".join(paragraphs)
