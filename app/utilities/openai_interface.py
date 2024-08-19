import os
from pathlib import Path
import openai
import chardet
from PyPDF2 import PdfReader
from app.utilities.prompt_optimization import dspy_model, simple_qa_model
import tiktoken

# 128K is the max context length for the GPT-4o model
# we use less than this to be safe
max_context_length = 90000


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


def extract_text_from_pdf(pdf_path):
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text()
    return text


# TODO we might need to rename the class
class OpenAIInterface:
    loaded_doc = ""

    def load_document(self, root_path, document_path):
        full_path = os.path.join(root_path, "static", "uploads", document_path)
        self.loaded_doc = extract_text_from_pdf(full_path)

    def ask_question_to_loaded_document(self, item):
        openai.api_key = "***REMOVED***"
        prompt = ""
        print("asking question")
        if len(item.text_blocks) > 0:
            prompt = (
                """Given the following document, and the attached additional context, answer the following question. Return the result as nicely formatted html.\nQuestion:\n"""
                + item.searchphrase
            )

            for block in item.text_blocks:
                prompt += "\n\nContext:\n" + block

            prompt += "\n\nDocument:\n" + self.loaded_doc
            # print(prompt)
        else:
            print("no text blocks")
            prompt = (
                """Given the following document, answer the following question. Return the result as nicely formatted html.:\nQuestion:\n"""
                + item.searchphrase
                + "\Document:\n"
                + self.loaded_doc
            )

        completion = openai.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
        )
        return completion.choices[0].message.content

    def ask_question_to_documents(
        self, root_path, documents, question, default_docs=[]
    ):

        full_text = ""
        if len(default_docs) > 0:
            # full_text += "# Default Context: "
            for doc in default_docs:
                full_path = os.path.join(root_path, "static", "uploads", doc.path)
                full_text += "\n\nDocument: " + extract_text_from_pdf(full_path) + " "

        # if len(documents) > 0:
        # full_text += "# Additional Context: "

        for document in documents:
            full_path = os.path.join(root_path, "static", "uploads", document.path)
            full_text += "\n\nDocument: " + extract_text_from_pdf(full_path) + " "

        openai.api_key = "***REMOVED***"
        prompt = (
            """Given the following document(s), answer the following question. Return the result as nicely formatted html with supportive information as if to display in a web interface chat bot. The html tags should fit nicely in a div on the page and not break formatting.
            \n\nQuestion: """
            + question
            + "\n\n"
        )
        print("prompt: ", prompt)
        prompt += full_text
        # use a tiktoken library for more accurate computation of the total token length for the context
        total_context_length = num_tokens_from_text(prompt)
        print("total context length: ", total_context_length)
        print("docs", documents)
        formatting_prompt = """Format the following answer to the given question as a nicely formatted html with supportive information to display in a web interface chat bot. The html tags should fit nicely in a div on the page and not break formatting. Do not add ```html before your response. Do not add 'Question', 'Answer', or 'Context' heading or title in your response, but respond only with the formatted html code for the answer.\n\n Question: """

        if total_context_length > max_context_length:
            print("using dspy model")
            print("question: ", question)

            persistent_directory = Path(root_path) / "static" / "uploads"
            collection_name = "chat_dspy_model"
            model = dspy_model(full_text, collection_name, persistent_directory)
            response = model(question=question)
            output_prompt = (
                formatting_prompt + question + "\n\nAnwsers: " + response.answer
            )
            print("dspy response: ", response.answer)
            # print("dspy model generated queries: ", queries)
            completion = openai.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": output_prompt}],
            )
            print("llm formatted response: ", completion.choices[0].message.content)
            formatted_answer = completion.choices[0].message.content
            return dict(
                context=response.context,
                answer=response.answer,
                formatted_answer=formatted_answer,
                question=question,
            )
        else:
            simple_qa = simple_qa_model()
            response = simple_qa(question=question, full_text=full_text)
            output_prompt = (
                formatting_prompt + question + "\n\nAnwsers: " + response.answer
            )
            completion = openai.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": output_prompt}],
            )
            formatted_answer = completion.choices[0].message.content

            return dict(
                context=response.context,
                answer=response.answer,
                formatted_answer=formatted_answer,
                question=question,
            )
