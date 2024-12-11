import os
from pathlib import Path
import openai
from PyPDF2 import PdfReader
from app.utilities.llm import ChatLM
from app.utilities.prompt_optimization import (
    dspy_model,
    simple_qa_model,
)

from app.models import ChatHistory, ChatMessage, ChatRole, MAX_CHAT_MESSAGES
from app.utilities.document_readers import extract_text_from_pdf, extract_text_from_doc

from app.utilities.llm_helpers import num_tokens_from_text
from app.utilities.config import max_context_length, model_type


# TODO we might need to rename the class
class OpenAIInterface:
    loaded_doc = ""

    def load_document(self, root_path, document_path):
        full_path = os.path.join(root_path, "static", "uploads", document_path)
        self.loaded_doc = extract_text_from_pdf(full_path)

    def ask_question_to_loaded_document(self, item):
        openai.api_key = "sk-proj-Tdb51ojrv5lwDtPH9S3tT3BlbkFJ6ty7hYO3Ow8weqXu6UjM"
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

        chat_lm = ChatLM(model_type)
        completion = chat_lm.completion(
            messages=[{"role": "user", "content": prompt}],
        )
        return completion

    def format_answer(self, response, question):
        formatting_prompt = """Format the following answer as a nicely formatted html with supportive information to display in a web interface chat bot. The html tags should fit nicely in a div on the page and not break formatting. Do not add ```html before your response. Do not add 'Question', 'Answer', 'Document', 'Next Sheet', 'Previous Sheet', or 'Context' any heading or title in your response, but respond only with the formatted html code for the answer.\n\n"""
        output_prompt = formatting_prompt + "\n\nAnwser: " + response.answer
        chat_lm = ChatLM(model_type)
        completion = chat_lm.completion(
            messages=[{"role": "user", "content": output_prompt}],
            max_tokens=None,
        )
        print("llm formatted response: ", completion)
        formatted_answer = completion
        return dict(
            context=response.context,
            answer=response.answer,
            formatted_answer=formatted_answer,
        )

    def handle_long_context(self, **kwargs):
        question = kwargs.get("question")
        full_text = kwargs.get("full_text", "")
        print("Long context needed")
        print("question: ", question)
        root_path = kwargs.get("root_path", "")

        print("using dspy model")
        print("question: ", question)

        persistent_directory = Path(root_path) / "static" / "uploads"
        collection_name = "chat_dspy_model"
        rag_model = dspy_model(
            full_text, collection_name, persistent_directory, model_type="insight"
        )
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

        openai.api_key = "sk-proj-Tdb51ojrv5lwDtPH9S3tT3BlbkFJ6ty7hYO3Ow8weqXu6UjM"

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
