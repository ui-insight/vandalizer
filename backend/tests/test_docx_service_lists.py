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


def test_json_string_of_a_mixed_list_renders_as_bullets():
    # The shape a model step usually hands over: JSON text, not a Python list.
    doc = _open(data_to_docx_bytes('[{"sponsor": "NSF"}, "No further awards found."]'))

    assert doc.tables == []
    assert "No further awards found." in _text(doc)


def test_nested_object_in_a_bullet_keeps_accented_text():
    doc = _open(data_to_docx_bytes(["Awards:", {"pi": "José Núñez"}]))

    assert '{"pi": "José Núñez"}' in _text(doc)


MIXED = [{"sponsor": "NSF", "amount": 1200}, "No further awards found."]


class TestOtherExportsWithMixedLists:
    """The same first-item-only check sat in the CSV, text and Markdown writers."""

    def test_saved_csv(self, tmp_path):
        from app.services.output_handlers import _save_as_csv

        _save_as_csv(tmp_path / "out.csv", MIXED)

        assert "No further awards found." in (tmp_path / "out.csv").read_text()

    def test_saved_text(self, tmp_path):
        from app.services.output_handlers import _save_workflow_as_text

        _save_workflow_as_text(tmp_path / "out.txt", MIXED)

        assert "No further awards found." in (tmp_path / "out.txt").read_text()

    def test_markdown(self):
        from app.services.output_handlers import _render_chainable_text, render_workflow_markdown

        assert "No further awards found." in render_workflow_markdown(MIXED)
        assert "No further awards found." in _render_chainable_text(MIXED, "wf")

    def test_data_export_step_csv(self):
        from app.services.workflow_engine import DataExportNode

        node = DataExportNode({"format": "csv", "filename": "export"})
        result = node.process({"output": MIXED})

        assert "error" not in result or not result["error"]

    def test_downloaded_csv(self):
        from app.routers.workflows import _render_workflow_output

        content, *_ = _render_workflow_output(
            {"workflow_name": "wf", "final_output": {"output": MIXED}}, "csv", False,
        )

        assert b"No further awards found." in content
