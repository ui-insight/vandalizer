import os
from pathlib import Path
import openai
import chardet
from PyPDF2 import PdfReader
from app.utilities.prompt_optimization import (
    dspy_model,
    simple_qa_model,
)
import tiktoken

from app.models import ChatHistory, ChatMessage, ChatRole, MAX_CHAT_MESSAGES
from app.utilities.document_readers import extract_text_from_pdf, extract_text_from_doc

# 128K is the max context length for the GPT-4o model
# we use less than this to be safe
# max_context_length = 16 * 1024  # 16k tokens
max_context_length = 90 * 1024  # 90k tokens


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
            # model="gpt-4o",
            model="gpt-4o-2024-08-06",
            messages=[{"role": "user", "content": prompt}],
        )
        return completion.choices[0].message.content

    def markdown_format(self, response):
        formatting_prompt = """Format the following answer as a nicely markdown. Do not add ```markdown before your response.\n\n"""
        output_prompt = formatting_prompt + "\n\nAnwser: " + response.answer
        # print("dspy model generated queries: ", queries)
        completion = openai.chat.completions.create(
            # model="gpt-4o",
            model="gpt-4o",
            messages=[{"role": "user", "content": output_prompt}],
            max_tokens=None,
        )
        return completion.choices[0].message.content

    def format_answer(self, response, question):
        formatting_prompt = """Format the following answer as a nicely formatted html with supportive information to display in a web interface chat bot. The html tags should fit nicely in a div on the page and not break formatting. Do not add ```html before your response. Do not add 'Question', 'Answer', 'Document', 'Next Sheet', 'Previous Sheet', or 'Context' any heading or title in your response, but respond only with the formatted html code for the answer.\n\n"""
        output_prompt = formatting_prompt + "\n\nAnwser: " + response.answer
        # print("dspy model generated queries: ", queries)
        completion = openai.chat.completions.create(
            # model="gpt-4o",
            model="gpt-4o",
            messages=[{"role": "user", "content": output_prompt}],
            max_tokens=None,
        )
        print("llm formatted response: ", completion.choices[0].message.content)
        formatted_answer = completion.choices[0].message.content
        markdown_answer = self.markdown_format(response)
        return dict(
            context=response.context,
            answer=response.answer,
            formatted_answer=formatted_answer,
            markdown_answer=markdown_answer,
        )

    def handle_long_context(self, **kwargs):
        question = kwargs.get("question")
        full_text = kwargs.get("full_text")
        print("Long context needed")
        print("question: ", question)
        root_path = kwargs.get("root_path")

        print("using dspy model")
        print("question: ", question)

        persistent_directory = Path(root_path) / "static" / "uploads"
        collection_name = "chat_dspy_model"
        rag_model = dspy_model(full_text, collection_name, persistent_directory)
        response = rag_model(question=question)

        print("dspy response: ", response.answer)
        return self.format_answer(response, question)

    def handle_short_context(self, **kwargs):
        prompt = kwargs.get("prompt")
        full_text = kwargs.get("full_text")
        print("Short context needed")

        simple_qa = simple_qa_model()
        response = simple_qa(question=prompt, full_text=full_text)

        print("simple qa response: ", response.answer)

        return self.format_answer(response, prompt)

    def ask_question_to_documents(
        self, root_path, documents, question, default_docs=[], user_id=None
    ):
        default_docs = list(default_docs)
        documents = list(documents)

        full_text = ""
        for document in default_docs + documents:
            full_path = os.path.join(root_path, "static", "uploads", document.path)
            print("full path: ", full_path)
            full_text += (
                "\n\nDocument: "
                + extract_text_from_doc(doc=document, doc_path=full_path)
                + " "
            )

        openai.api_key = "***REMOVED***"

        latest_conversation_messages = ChatHistory.get_latest_conversation_messages(
            user_id=user_id
        )
        previous_messages = []
        # if the number of messages in the conversation is less than the max chat messages
        if latest_conversation_messages is not None:
            previous_messages = latest_conversation_messages[-MAX_CHAT_MESSAGES:]

        print("previous messages: ", previous_messages)

        prompt = (
            """Given the following conversation history, document(s), answer the following question. Return the answer as nicely formatted html with supportive information to display in a web interface chat bot.
            \n\nQuestion: """
            + question
            + "\n\n"
        )
        # append the question to the previous messages
        prompt += "Conversation history: \n"
        for message in previous_messages:
            if message.role == ChatRole.USER:
                prompt += "User: " + message.message + "\n"
            elif message.role == ChatRole.SYSTEM:
                prompt += "System: " + message.message + "\n\n"

        print("prompt: ", prompt)

        # prompt += full_text
        # use a tiktoken library for more accurate computation of the total token length for the context
        # print("total context length: ", total_context_length)
        # print("docs", documents)

        output = self.perform_llm_call(
            prompt=prompt, question=question, full_text=full_text, root_path=root_path
        )

        if user_id is None:
            return output

        # save the conversation
        user_message = ChatMessage(
            role=ChatRole.USER,
            message=question,
        )
        system_message = ChatMessage(
            role=ChatRole.SYSTEM,
            message=output["formatted_answer"],
        )
        user_message.save()
        system_message.save()
        print("messages: ", previous_messages + [user_message, system_message])
        conversation = ChatHistory(
            user_id=user_id, messages=[user_message, system_message]
        )
        conversation.save()
        print("conversation saved", conversation)
        return output

    def perform_llm_call(self, prompt, **kwargs):
        full_text = kwargs.get("full_text")
        context = prompt + full_text if full_text else prompt

        total_context_length = num_tokens_from_text(context)
        print("total context length: ", total_context_length)
        print("max context length: ", max_context_length)
        if total_context_length > max_context_length:
            return self.handle_long_context(prompt=prompt, **kwargs)

        else:
            return self.handle_short_context(prompt=prompt, **kwargs)
