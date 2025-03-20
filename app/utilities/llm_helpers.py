#!/usr/bin/env python3

import json
import tiktoken
from typing import Any, List, Dict, Type
from pydantic import BaseModel, ValidationError
from app.utilities.config import model_type

# from langfuse.decorators import observe

import chardet

from app.utilities.llm import ChatLM


def remove_code_markers(text: str) -> str:
    """
    Removes code block markers and language specifiers from LLM responses.

    Args:
        answer (str): The raw LLM response text

    Returns:
        str: Formatted text with code blocks and language specifiers removed
    """
    # Split the text into lines
    lines = text.split("\n")
    formatted_lines = []
    skip_line = False

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
    formatted_text = "\n".join(formatted_lines)

    return formatted_text


# Implementation based on the discussion:
# https://community.openai.com/t/whats-the-new-tokenization-algorithm-for-gpt-4o/746708/3
# gpt-4o seems to be using "o200k_base" encoding
def num_tokens_from_text(text: str, model="gpt-4o"):
    """Return the number of tokens in a text string."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        print("Warning: model not found. Using cl100k_base encoding.")
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
    elif model == "gpt-3.5-turbo-0301":
        # This model might have slightly different tokenization
        print("Warning: gpt-3.5-turbo-0301 may have slightly different tokenization.")
        return len(encoding.encode(text))
    elif "gpt-3.5-turbo" in model:
        print("Warning: gpt-3.5-turbo may update over time. Using current encoding.")
        return len(encoding.encode(text))
    elif "gpt-4" in model:
        print("Warning: gpt-4 may update over time. Using current encoding.")
        return len(encoding.encode(text))
    else:
        raise NotImplementedError(
            f"""num_tokens_from_text() is not implemented for model {model}. See https://github.com/openai/openai-python/blob/main/chatml.md for information on how text is converted to tokens."""
        )


def detect_encoding(file_path):
    with open(file_path, "rb") as file:
        result = chardet.detect(file.read())
    return result["encoding"]


def process_large_prompt(
    client: Any,
    system_prompt: str,
    user_prompt: str,
    max_tokens=120000,
    model="gpt-4o",
    response_format={"type": "json_object"},
):
    """
    Process large prompts by chunking them while preserving the system prompt.

    Args:
        system_prompt (str): The system prompt to maintain context
        user_prompt (str): The user's input prompt
        model (str, optional): OpenAI model to use. Defaults to "gpt-3.5-turbo".
        max_tokens (int, optional): Maximum tokens to process in a single chunk. Defaults to 120000.

    Returns:
        str: Concatenated response from processing chunks
    """
    # Initialize tokenizer
    tokenizer = tiktoken.encoding_for_model(model)

    # Encode system and user prompts
    system_tokens = tokenizer.encode(system_prompt)
    user_tokens = tokenizer.encode(user_prompt)

    # Calculate available tokens for user prompt
    max_user_tokens = max_tokens - len(system_tokens)

    # Function to split tokens into chunks
    def chunk_tokens(tokens, chunk_size):
        return [tokens[i : i + chunk_size] for i in range(0, len(tokens), chunk_size)]

    # Split user prompt into chunks
    user_token_chunks = chunk_tokens(user_tokens, max_user_tokens)

    # Store full response
    full_response = []

    # Process each chunk
    for chunk_tokens in user_token_chunks:
        # Decode chunk tokens back to text
        chunk_text = tokenizer.decode(chunk_tokens)

        try:
            # Call OpenAI API with system prompt and current chunk

            chat_lm = ChatLM(model_type)
            print("model schema: ", response_format.model_json_schema())
            response = chat_lm.completion(
                structured_output=True,
                format=response_format.model_json_schema(),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": chunk_text},
                ],
            )
            print("response: ", response)

            # Append chunk response
            full_response.append(response)

        except Exception as e:
            print(f"Error processing chunk: {e}")
            # Optional: add error handling or logging
            break

    # Concatenate and return full response
    return " ".join(full_response)


# @observe
def retry_llm_request(
    client: Any,
    messages: List[Dict[str, str]],
    model_class: Type[BaseModel],
    max_retries: int = 5,
    model_type="openai",
):
    for attempt in range(max_retries):
        try:
            # data = process_large_prompt(
            #     system_prompt=messages[0]["content"],
            #     user_prompt=messages[1]["content"],
            #     client=client,
            #     response_format=model_class,
            # )

            chat_lm = ChatLM(model_type)
            system_prompt = messages[0]["content"]
            user_prompt = messages[1]["content"]
            response_format = model_class
            print("model schema: ", response_format)
            kwargs = dict()
            if model_type == "openai":
                kwargs["structured_output"] = True
                kwargs["model"] = "gpt-4o"
                kwargs["response_format"] = model_class
            else:
                kwargs = dict(
                    structured_output=True,
                    format=response_format,
                )

            response = chat_lm.completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                **kwargs,
            )
            print("response: ", response)
            if model_type == "openai":
                data = json.loads(response.choices[0].message.content)
                return data.get("entities", [])

            else:
                data = json.loads(response)
                return data.get("entities", [])

            # validated_output = model_class.model_validate(output)

            # print(f"Validation attempt {attempt + 1} succeeded.")
            # print("Validated Output: ", validated_output)
            # return validated_output
            #
            # result = data.model_dump_json(indent=2)
            # print("Result: ", result)
            # result = json.loads(result)
            # entities = result.get("entities", [])
            # return entities

        except ValidationError as ve:
            error_details = str(ve)

            improvement_prompt = (
                f"The previous JSON response failed validation. "
                f"Here are the specific validation errors:\n\n"
                f"{error_details}\n\n"
                f"Please correct the JSON to match the required structure. "
                f"Pay close attention to the following requirements:"
            )

            field_guidance = []
            for error in ve.errors():
                loc = " -> ".join(map(str, error["loc"]))
                field_guidance.append(
                    f"- Field {loc}: {error['msg']} (Type: {error.get('type', 'unspecified')})"
                )

            improvement_prompt += "\n" + "\n".join(field_guidance)

            messages.append({"role": "system", "content": improvement_prompt})

            print(
                f"Validation attempt {attempt + 1} failed. Retrying with detailed guidance."
            )
            print("Improvement Prompt: ", improvement_prompt)

    return (
        f"Failed to generate valid {model_class.__name__} after {max_retries} attempts"
    )
