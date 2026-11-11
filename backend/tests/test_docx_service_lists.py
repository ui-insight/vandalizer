"""Word export of list-shaped workflow output.

A list whose first item was an object but a later one was text crashed the
Document Renderer step with "'str' object has no attribute 'keys'".
"""

import io

from docx import Document

from app.services.docx_service import data_to_docx_bytes


def _open(payload: bytes):
    return Document(io.BytesIO(payload))


def _text(doc) -> str:
    return "\n".join(p.text for p in doc.paragraphs)


def test_list_of_objects_and_text_renders_as_bullets():
    data = [{"sponsor": "NSF", "amount": 1200}, "No further awards found."]

    doc = _open(data_to_docx_bytes(data))

    assert doc.tables == []
    text = _text(doc)
    assert '{"sponsor": "NSF", "amount": 1200}' in text
    assert "No further awards found." in text


def test_list_of_objects_still_renders_as_table():
    data = [{"sponsor": "NSF", "amount": 1200}, {"sponsor": "NIH", "pi": "Lee"}]

    doc = _open(data_to_docx_bytes(data))

    (table,) = doc.tables
    assert [c.text for c in table.rows[0].cells] == ["sponsor", "amount", "pi"]
    assert [c.text for c in table.rows[2].cells] == ["NIH", "", "Lee"]
