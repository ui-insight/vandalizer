"""Public usage summaries derived from published definitions, without private destinations."""
from __future__ import annotations


def describe_catalog_usage(kind: str, item, steps: list | None = None) -> dict:
    notes: list[str] = []
    outputs: list[str] = []
    if kind == "knowledge_base":
        input_text = "Ask a question about the indexed sources."
        output_text = "An answer with supporting source references when available."
        if not getattr(item, "total_chunks", 0):
            notes.append("No indexed content is available for chat yet.")
    elif kind == "search_set":
        if getattr(item, "set_type", None) == "prompt":
            input_text = "Review the saved instructions and provide the context they ask for."
            output_text = "A generated response from the saved prompt."
        else:
            input_text = "Choose the documents to extract from."
            output_text = "Structured values for the configured extraction fields."
    elif kind == "workflow":
        config = getattr(item, "input_config", None)
        config = config if isinstance(config, dict) else {}
        trigger = config.get("trigger_type")
        fixed = config.get("fixed_documents")
        fixed_count = len(fixed) if isinstance(fixed, list) else 0
        if trigger == "text_input":
            input_text = "Paste or type the text to process. Selected documents can also be included."
        elif trigger == "no_input":
            input_text = "No manual run input is required by this workflow's configuration."
        elif fixed_count:
            input_text = "Uses configured fixed documents; you can also select documents."
        else:
            input_text = "Select documents or use the active project's files."
        if fixed_count:
            notes.append(f"{fixed_count} fixed document{'s' if fixed_count != 1 else ''} configured; access is checked at run time.")
        executable = [s for s in (steps or []) if not (s.name == "Document" and not s.tasks)]
        if executable:
            outputs = [s.name for i, s in enumerate(executable) if s.is_output or i == len(executable) - 1]
            output_text = "Results from the workflow's output steps."
        else:
            output_text = "No executable output steps are configured."
    else:
        input_text = "Input requirements are not described."
        output_text = "Expected output is not described."
    return {"input": input_text, "output": output_text, "output_names": outputs, "notes": notes}
