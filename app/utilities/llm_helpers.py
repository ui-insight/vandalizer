#!/usr/bin/env python3

import json
from typing import Any

# from langfuse.decorators import observe
import chardet
import tiktoken
from pydantic import BaseModel, ValidationError

from app.utilities.config import settings
from app.utilities.llm import ChatLM


def remove_code_markers(text: str) -> str:
    """Removes code block markers and language specifiers from LLM responses.

    Args:
        answer (str): The raw LLM response text

    Returns:
        str: Formatted text with code blocks and language specifiers removed

    """
    # Split the text into lines
    lines = text.split("\n")
    formatted_lines = []

    for line in lines:
        # Check for code block markers with or without language specification
        if "```" in line:
            # If line only contains the code block marker with optional language
            if line.strip().startswith("```") and len(line.strip().split()) <= 2:
                continue
            # If code block marker is part of a content line, remove just the markers
            line = line.replace("```", "")

        formatted_lines.append(line)

    # Join the lines back together
    return "\n".join(formatted_lines)


# Implementation based on the discussion:
# https://community.openai.com/t/whats-the-new-tokenization-algorithm-for-gpt-4o/746708/3
# gpt-4o seems to be using "o200k_base" encoding
def num_tokens_from_text(text: str, model="gpt-4o"):
    """Return the number of tokens in a text string."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")

    # List of models that use the same tokenizer
    if model in {
        "gpt-3.5-turbo-0613",
        "gpt-3.5-turbo-16k-0613",
        "gpt-4-0314",
        "gpt-4-32k-0314",
        "gpt-4-0613",
        "gpt-4-32k-0613",
        "gpt-4-turbo",
        "gpt-4-turbo-2024-04-09",
        "gpt-4o",
        "gpt-4o-2024-05-13",
    }:
        # These models use the same tokenizer, so we can just encode and count
        return len(encoding.encode(text))
    if model == "gpt-3.5-turbo-0301":
        # This model might have slightly different tokenization
        return len(encoding.encode(text))
    if "gpt-3.5-turbo" in model:
        return len(encoding.encode(text))
    if "gpt-4" in model:
        return len(encoding.encode(text))
    msg = f"""num_tokens_from_text() is not implemented for model {model}. See https://github.com/openai/openai-python/blob/main/chatml.md for information on how text is converted to tokens."""
    raise NotImplementedError(
        msg,
    )
