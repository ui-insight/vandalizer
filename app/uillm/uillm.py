import base64
import json
import os
import re

import requests
from jsonschema import SchemaError, ValidationError, validate

# Ensure this is the intended client library for your use case

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------


def format_content(content, _type, fmt='jpeg', isStructured=False):
    """
    Formats the content into a dictionary suitable for posting to the LLM endpoint.

    Args:
        content (str or bytes): The content to be formatted (e.g., text, image path/URL, or PDF).
        _type (str): The type of content. Acceptable values are 'text', 'image_url', 'image_base64', 'pdf', or 'pdf_url'.

    Returns:
        dict: A dictionary with the formatted content.

    Raises:
        ValueError: If an unsupported content type is provided.
    """
    if _type == "text":
        content_dict = {"type": _type, "text": content}
    elif _type == "image_url":
        image_content = get_image_from_source(content)
        if isStructured:
            content_dict = image_content
        else:
            content_dict = {
                "type": _type,
                "image_url": {"url": f"data:image/{fmt};base64,{image_content}"},
            }
    elif _type == "image_base64":
        if isStructured:
            content_dict = f"data:image/{fmt};base64,{content}"
        else:
            content_dict = {
                "type": "image_url",
                "image_url": {"url": f"data:image/{fmt};base64,{content}"},
            }
    elif _type in ["pdf", "pdf_url"]:
        pdf_content = convert_pdf(content, _type)
        # Convert the PDF output to text (using an OCR service)
        content_dict = {"type": "text", "text": pdf_content}
    else:
        raise ValueError(f"Error: invalid content type {_type}")

    return content_dict


def handle_output(response, model):
    """
    Processes the response from the LLM endpoint based on the model type.

    Args:
        response: The HTTP response or OpenAI response object.
        model (str): The model used to generate the response.

    Returns:
        str: The content extracted from the response.
    """
    if model in ["gpt-4o", "gpt-4o-mini", "o1-preview", "o1-mini"]:
        try:
            content = response.choices[0].message.content
        except Exception as e:
            print(f"ERROR: {e}")
            content = ""
    else:
        status = response.status_code
        if status == 200:
            try:
                output = response.json()
                content = output["choices"][0]["message"]["content"]
                if content is None:
                    print("Failed on output:", output)
            except json.JSONDecodeError:
                print("Invalid JSON format")
                print(response.text)
                content = ""
        else:
            print("SERVER ERROR")
            print(response.status_code)
            print(response.text)
            content = ""
    return content


def handle_output_from_chat_api(response, model):
    """
    Processes the response from the LLM endpoint based on the model type.

    Args:
        response: The HTTP response or OpenAI response object.
        model (str): The model used to generate the response.

    Returns:
        str: The content extracted from the response.
    """

    status = response.status_code
    if status == 200:
        try:
            output = response.json()

            content = output["message"]["content"]
            if content is None:
                print("Failed on output:", output)
        except (KeyError, json.JSONDecodeError) as e:
            print("Invalid JSON format")
            print(response.text)
            content = ""
    else:
        print("SERVER ERROR")
        print(response.status_code)
        print(response.text)
        content = ""
    return content


def handle_structured_output(response, model):
    """
    Processes the response from the LLM endpoint based on the model type.

    Args:
        response: The HTTP response or OpenAI response object.
        model (str): The model used to generate the response.

    Returns:
        str: The content extracted from the response.
    """

    status = response.status_code
    if status == 200:
        try:
            output = response.json()
            content = output["response"]
            if content is None:
                print("Failed on output:", output)
        except (KeyError, json.JSONDecodeError) as e:
            print("Invalid JSON format")
            print(response.text)
            content = ""
    else:
        print("SERVER ERROR")
        print(response.status_code)
        print(response.text)
        content = ""
    return content


def convert_pdf(content, _type):
    """
    Converts a PDF document to text using an external OCR service.

    Args:
        content (str or bytes): The PDF file content or source URL/path.
        _type (str): Either "pdf" or "pdf_url" to indicate the source type.

    Returns:
        str: The text extracted from the PDF.
    """
    endpoint = "https://ocr.insight.uidaho.edu/ocr"

    if _type == "pdf_url":
        file = get_pdf_from_source(content)
        files = {"file": file}
    else:
        files = {"file": content}

    try:
        response = requests.post(endpoint, files=files, timeout=300)
    except Exception as e:
        print(f"Error during PDF conversion: {e}")
        return ""
    return response.text


def get_image_from_source(image_source):
    """
    Returns a base64 encoded string of an image from a local path or a URL.

    Args:
        image_source (str): A local file path or URL for the image.

    Returns:
        str: A base64 encoded string of the image.

    Raises:
        ValueError: If the image cannot be retrieved or processed.
    """
    try:
        if os.path.isfile(image_source):
            with open(image_source, "rb") as img_file:
                image_bytes = img_file.read()
        else:
            response = requests.get(image_source)
            response.raise_for_status()
            image_bytes = response.content

        base64_encoded = base64.b64encode(image_bytes).decode("utf-8")
        return base64_encoded

    except Exception as e:
        raise ValueError(f"Could not process image: {e}")


def get_pdf_from_source(pdf_source):
    """
    Returns the binary content of a PDF file from a local path or URL.

    Args:
        pdf_source (str): A local file path or URL for the PDF.

    Returns:
        bytes: The binary content of the PDF file.

    Raises:
        ValueError: If the PDF cannot be retrieved.
    """
    try:
        if os.path.isfile(pdf_source):
            with open(pdf_source, "rb") as pdf_file:
                return pdf_file.read()
        else:
            response = requests.get(pdf_source)
            response.raise_for_status()
            return response.content

    except Exception as e:
        raise ValueError(f"Could not process PDF: {e}")


# -----------------------------------------------------------------------------
# UILLM Class
# -----------------------------------------------------------------------------


class UILLM:
    """
    A collection of static methods for interacting with the LLM endpoint,
     including asking questions, handling additional content (e.g., images, PDFs),
     listing models, and converting strings to embeddings.
    """

    @staticmethod
    def ask_question(
        question,
        content=None,
        content_type=None,
        content_format=None,
        is_json=False,
        structured_format=None,
        model="",
        temperature=0.7,
        max_tokens=None,
        system_message=None,
        stream=False,
        **kwargs,
    ):
        """
        Sends a query to the LLM endpoint, supporting text-only, structured output,
        and multi-content queries.

        Args:
            question (str): The primary question or prompt.
            content (Union[object, List[object]], optional): Additional content (e.g., images, PDFs).
            content_type (Union[str, List[str]], optional): Type(s) of additional content.
            content_format (Union[str, List[str]], optional): Document format(s) of additional content (e.g pdf, png, jpeg, txt, etc).
            is_json (bool): Whether to request a JSON-formatted response.
            structured_format (dict, optional): JSON Schema for structured output.
            model (str): The model to use (defaults based on content type if not specified).
            temperature (float): Controls response randomness (default: 0.7).
            max_tokens (int, optional): Maximum tokens for output.
            api_key (str): API key for multi-content queries with OpenAI models.
            system_message (str, optional): Optional system message to include.
            **kwargs: Additional options for the request.

        Returns:
            str or dict: The model's response, either as text or a JSON object.

        Raises:
            UserWarning: If API key is missing for multi-content queries or if content is provided without content_type.
        """
        import json  # Ensure json is imported if not already

        # Define endpoints
        base_endpoint = "https://mindrouter-api.nkn.uidaho.edu"
        chat_endpoint = f"{base_endpoint}/v1/chat/completions"
        ollama_endpoint = f"{base_endpoint}/api/generate"

        # Set default model based on content and structured format
        if not model:
            if content and any(
                ct in ["image_url", "image_base64"]
                for ct in (
                    [content_type] if isinstance(content_type, str) else content_type
                )
            ):
                model = "llava-llama3:8b"
            elif content:
                model = "qwen2.5-8k:72b"
            else:
                model = "llama3.1:70b"

        headers = {"Content-Type": "application/json", "Authorization": "Bearer no-key"}

        # If structured_format (or additional options) are provided, use the /api/generate endpoint
        if structured_format or system_message or max_tokens or kwargs:
            options = kwargs.copy()
            options["temperature"] = temperature
            if max_tokens:
                options["num_predict"] = max_tokens

            # Start building the payload with a direct prompt
            data = {
                "model": model,
                "prompt": question,
                "stream": stream,
                "temperature": temperature,
                "options": options,
            }

            # Incorporate additional content if provided
            if content is not None:
                if content_type is None or content_format is None:
                    raise UserWarning(
                        "content_type and content_format must be provided when content is specified."
                    )

                # Ensure content and content_type are lists
                content = content if isinstance(content, list) else [content]
                content_type = (
                    content_type if isinstance(content_type, list) else [content_type]
                )

                # Separate image content from text content
                images = []
                extra_texts = []
                for item, ct, fmt in zip(content, content_type, content_format):
                    if ct in ["image_url", "image_base64"]:
                        # Assume format_content returns the properly formatted image data
                        images.append(format_content(item, ct, fmt, isStructured=True))
                    else:
                        extra_texts.append(str(item))
                if images:
                    data["images"] = images
                if extra_texts:
                    data["prompt"] += "\n" + "\n".join(extra_texts)

            # Add the structured format to the payload if provided
            if structured_format:
                data["format"] = structured_format

            response = requests.post(ollama_endpoint, json=data, headers=headers)
            content_response = handle_structured_output(response, model)

            if structured_format and content_response:
                try:
                    parsed = json.loads(content_response)
                    # Validate against the JSON schema if needed
                    validate(instance=parsed, schema=structured_format)
                    return parsed
                except (json.JSONDecodeError, ValidationError, SchemaError) as e:
                    print(f"Invalid JSON or schema validation failed: {e}")
                    return content_response
            return content_response
        else:
            # For non-structured queries, build the chat-style payload
            messages = []
            if system_message:
                messages.append({"role": "system", "content": system_message})
            if content is not None:
                if content_type is None or content_format is None:
                    raise UserWarning(
                        "content_type and content_format must be provided when content is specified."
                    )
                content = content if isinstance(content, list) else [content]
                content_type = (
                    content_type if isinstance(content_type, list) else [content_type]
                )
                # Build the message content with the prompt and any additional content
                message_content = [{"type": "text", "text": question}] + [
                    format_content(item, ct, isStructured=False)
                    for item, ct in zip(content, content_type)
                ]
                messages.append({"role": "user", "content": message_content})
            else:
                messages.append({"role": "user", "content": question})
            data = {"model": model, "temperature": temperature, "messages": messages}
            if is_json:
                data["response_format"] = {"type": "json_object"}

            response = requests.post(chat_endpoint, json=data, headers=headers)
            content_response = handle_output(response, model)
            if is_json and content_response:
                try:
                    return json.loads(content_response)
                except json.JSONDecodeError:
                    print("Invalid JSON format in response.")
                    return content_response
            return content_response

    @staticmethod
    def list_models(display="pretty", verbose=False):
        """
        Lists the available models from the endpoint.

        Args:
            display (str): How to display the models ('pretty' for formatted printing or 'list' for a name list).
            verbose (bool): If True, prints additional information.

        Returns:
            list (optional): If display is 'list', returns a list of model names.
        """
        endpoint = "https://mindrouter-api.nkn.uidaho.edu/api/tags"
        response = requests.get(endpoint)
        if verbose:
            print(response.text)
        try:
            data = response.json()
        except json.JSONDecodeError:
            print("Error decoding models data.")
            return

        if display == "pretty":
            return UILLM.display_models(data)
        elif display == "list":
            return UILLM.display_models_list(data)

    @staticmethod
    def display_models_list(data):
        """
        Returns a list of model names extracted from the data.

        Args:
            data (dict): The JSON data containing models.

        Returns:
            list: A list of model names.
        """
        return [x.get("name") for x in data.get("models", [])]

    @staticmethod
    def display_models(data):
        """
        Prints the details of available models in a formatted manner.

        Args:
            data (dict): The JSON data containing models.
        """
        models = data.get("models", [])
        if not models:
            print("No models available.")
            return

        return_str = ""

        for model in models:
            name = model.get("name", "N/A")
            details = model.get("details", {})
            family = details.get("family", "N/A")
            parameter_size = details.get("parameter_size", "N/A")
            quantization_level = details.get("quantization_level", "N/A")

            print(f"Model: {name}")
            return_str += f"Model: {name}\n"
            print("  Details:")
            return_str += "  Details:\n"
            print(f"    Family: {family}")
            return_str += f"    Family: {family}\n"
            print(f"    Parameter Size: {parameter_size}")
            return_str += f"    Parameter Size: {parameter_size}\n"
            print(f"    Quantization Level: {quantization_level}")
            return_str += f"    Quantization Level: {quantization_level}\n"
            print("-" * 40)
            return_str += "-" * 40 + "\n"

        return return_str

    @staticmethod
    def list_reasoning(display="pretty", verbose=False):
        """
        Lists only models known for chain-of-thought and reasoning capabilities
        from the endpoint.

        Args:
            display (str): 'pretty' to format output, 'list' to return names.
            verbose (bool): If True, prints raw JSON response.

        Returns:
            list (optional): If display == 'list', returns a list of reasoning model names.
        """
        endpoint = "https://mindrouter-api.nkn.uidaho.edu/api/tags"
        response = requests.get(endpoint)
        if verbose:
            print(response.text)
        try:
            data = response.json()
        except json.JSONDecodeError:
            print("Error decoding models data.")
            return

        # Families optimized for chain-of-thought / reasoning
        reasoning_tags = [
            "command-r",  # Cohere’s Command R family
            "deepseek-r1",  # DeepSeek‑R1 series
            "llama3.3",  # Meta Llama 3.3
            "phi-4",  # Microsoft’s Phi‑4
        ]

        # Filter for reasoning models
        reasoning_models = [
            m
            for m in data.get("models", [])
            if any(m.get("name", "").lower().startswith(tag) for tag in reasoning_tags)
        ]

        filtered_data = {"models": reasoning_models}

        if display == "pretty":
            return UILLM.display_models(filtered_data)
        elif display == "list":
            return UILLM.display_models_list(filtered_data)
        

    @staticmethod
    def list_vision(display="pretty", verbose=False):
        """
        Lists only models known for chain-of-thought and reasoning capabilities
        from the endpoint.

        Args:
            display (str): 'pretty' to format output, 'list' to return names.
            verbose (bool): If True, prints raw JSON response.

        Returns:
            list (optional): If display == 'list', returns a list of reasoning model names.
        """
        endpoint = "https://mindrouter-api.nkn.uidaho.edu/api/tags"
        response = requests.get(endpoint)
        if verbose:
            print(response.text)
        try:
            data = response.json()
        except json.JSONDecodeError:
            print("Error decoding models data.")
            return

        # Families optimized for chain-of-thought / reasoning
        reasoning_tags = [
            "gemma3",  # Gemma family
            "mistralai",  # mistral/pixtral proxy
            "llama3.2-vision",  # Meta Llama 3.2 vision variant
            "microsoft",  # Microsoft’s Phi‑4
            "openai", #openai proxies
            "llava", # llava vision models
            "google", #google-gemini proxies
        ]

        # Filter for reasoning models
        reasoning_models = [
            m
            for m in data.get("models", [])
            if any(m.get("name", "").lower().startswith(tag) for tag in reasoning_tags)
        ]

        filtered_data = {"models": reasoning_models}

        if display == "pretty":
            UILLM.display_models(filtered_data)
        elif display == "list":
            return UILLM.display_models_list(filtered_data)

    @staticmethod
    def list_suggested(display="pretty", verbose=False):
        """
        Lists the most popular models based on industry usage.

        Args:
            display (str): 'pretty' to format output, 'list' to return names.
            verbose (bool): If True, prints raw JSON response.

        Returns:
            list (optional): If display == 'list', returns a list of popular model names.
        """
        endpoint = "https://mindrouter-api.nkn.uidaho.edu/api/tags"
        response = requests.get(endpoint)
        if verbose:
            print(response.text)
        try:
            data = response.json()
        except json.JSONDecodeError:
            print("Error decoding models data.")
            return

        # Families most frequently cited as top-tier in editorial roundups
        popular_tags = [
            "openai/gpt-4o",  # GPT-4o
            "openai/gpt-4.1-mini",  # GPT-4.1 Mini
            "google/gemini-2.0-flash",  # Gemini 2.0 Flash
            "anthropic/claude-3.7-sonnet",  # Claude 3.7 Sonnet
            "x-ai/grok-2",  # Grok
            "deepseek-r1",  # DeepSeek R1
            "command-r-plus",  # Command R+
            "qwen2.5",
        ]

        # Filter models whose name or family matches one of the popular tags
        popular_models = [
            m
            for m in data.get("models", [])
            if any(m.get("name", "").lower().startswith(tag) for tag in popular_tags)
        ]

        filtered_data = {"models": popular_models}
        if display == "pretty":
            return UILLM.display_models(filtered_data)
        elif display == "list":
            return UILLM.display_models_list(filtered_data)

    @staticmethod
    def parse_command_R(data):
        """
        Extracts and fixes JSON content from a string output (from command-R).

        Args:
            data (str): The string data containing JSON.

        Returns:
            dict: The parsed JSON content.

        Raises:
            ValueError: If no JSON is found or if parsing fails.
        """
        # Strip leading and trailing newlines
        data = data.strip("\n")
        # Extract JSON part using regex
        json_match = re.search(r"{.*}", data, re.DOTALL)
        if not json_match:
            raise ValueError(
                f"Unexpected response from command-R. JSON string not found in data: {data}"
            )

        json_str = json_match.group(0).strip()
        # Attempt to fix formatting issues (e.g., missing quotes around keys)
        json_str = re.sub(r'(?<!")(\b\w+\b)(?!")(?=\s*:)', r'"\1"', json_str)
        json_str = re.sub(r'(?<=["\]}])\s*(?=["\[{])', ",", json_str)
        try:
            parsed_json = json.loads(json_str)
            return parsed_json
        except json.JSONDecodeError as e:
            print(
                f"Invalid JSON provided by command-R. Error: {e.msg}, Content: {json_str}"
            )
            raise e

    @staticmethod
    def convert_string_to_embeddings(string, model="EMBED/all-minilm:22m"):
        """
        Converts a given string into embeddings using the specified model.

        Args:
            string (str): The string to be converted.
            model (str): The model to use for embeddings.

        Returns:
            dict: The embeddings data if successful; otherwise, prints error information.
        """
        endpoint = "https://mindrouter-api.nkn.uidaho.edu/api/embeddings"
        data = {"model": model, "prompt": string}
        response = requests.post(endpoint, json=data)
        if response.status_code == 200:
            return response.json()
        else:
            print("SERVER ERROR")
            print(response.status_code)
            print(response.text)
            return None