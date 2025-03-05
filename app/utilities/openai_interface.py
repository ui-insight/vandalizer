import os
from datetime import datetime
from devtools import debug

import json
import re
from pathlib import Path
import openai
from PyPDF2 import PdfReader
from app.utilities.agents import RagDeps, rag_agent, chat_agent
from app.utilities.document_manager import DocumentManager
from app.utilities.llm import ChatLM
from app.utilities.prompt_optimization import (
    multi_qa,
    simple_qa,
)
from langfuse.decorators import observe
import asyncio


from app.utilities.async_utilities import class_method_event_loop_decorator

import time

# from langchain_redis import RedisCache
from app.utilities.redis_cache import RedisCache

from app.models import (
    ChatHistory,
    ChatMessage,
    ChatRole,
    MAX_CHAT_MESSAGES,
    AgentHistory,
)
from app.utilities.document_readers import extract_text_from_pdf, extract_text_from_doc

from app.utilities.llm_helpers import num_tokens_from_text
from app.utilities.config import max_context_length, model_type
from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
    SystemPromptPart,
)

# 2h
ttl = 60 * 60 * 1
cache = RedisCache(redis_url="redis://localhost:6379", ttl=ttl)

# TODO remove the formatting of the answer from the OpenAIInterface class
# it is taking so much time to execute the call


# TODO we might need to rename the class
class OpenAIInterface:
    loaded_doc = ""

    def load_document(self, root_path, document_path):
        full_path = os.path.join(root_path, "static", "uploads", document_path)
        self.loaded_doc = extract_text_from_pdf(full_path)

    @observe()
    def ask_question_to_loaded_document(self, item):
        openai.api_key = os.getenv("OPENAI_API_KEY")
        prompt = ""
        print("asking question")
        if len(item.text_blocks) > 0:
            prompt = (
                """Given the following document, and the attached additional context, answer the following question. Return the result as nicely formatted html div.\nQuestion:\n"""
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
                + "\n\nDocument:\n"
                + self.loaded_doc
            )

        chat_lm = ChatLM(model_type)
        completion = chat_lm.completion(
            messages=[{"role": "user", "content": prompt}],
        )
        return completion

    # def format_answer(self, answer):
    #     regex = r"^```(html|json|markdown)?\s*|\s*```$"
    #     formatted_answer = re.sub(regex, "", answer)
    #     return formatted_answer
    def format_answer(self, answer):
        """
        Removes code block markers and language specifiers from LLM responses.

        Args:
            answer (str): The raw LLM response text

        Returns:
            str: Formatted text with code blocks and language specifiers removed
        """
        # Split the text into lines
        lines = answer.split("\n")
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
        formatted_answer = "\n".join(formatted_lines)

        return formatted_answer

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
        response = multi_qa(
            full_text,
            collection_name,
            persistent_directory,
            model_type=model_type,
        )

        print("dspy response: ", response.answer)
        # return self.format_answer(response, question)
        return dict(
            answer=self.format_answer(response.answer),
            formatted_answer=self.format_answer(response.answer),
            context=response.context,
            question=question,
        )

    def handle_short_context(self, **kwargs):
        prompt = kwargs.get("prompt")
        question = kwargs.get("question")
        full_text = kwargs.get("full_text")
        print("Short context needed")

        response = simple_qa(
            question=prompt, full_text=full_text, model_type=model_type
        )

        print("simple qa response: ", response.answer)

        # return self.format_answer(response, prompt)
        #
        return dict(
            answer=self.format_answer(response.answer),
            formatted_answer=self.format_answer(response.answer),
            context=response.context,
            question=question,
        )

    @class_method_event_loop_decorator()
    def ask_question_to_documents(
        self,
        root_path,
        documents,
        question,
        session=None,
        user_id=None,
        default_docs=[],
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

        openai.api_key = os.getenv("OPENAI_API_KEY")


        docs_ids_string = "_".join([str(doc.id) for doc in documents])
        cache_key = f"chat_history_{user_id}_{docs_ids_string}"
        llm_string = "pydantic_model:openai:gpt-4o"
        previous_messages = []
        latest_conversation_messages = []
        if session is not None:
            # latest_conversation_messages = session.get("chat_history", [])
            cache_result = cache.lookup(cache_key, llm_string)
            if cache_result is not None:
                debug(cache_result)
                latest_conversation_messages = cache_result

                # latest_conversation_messages =
                ModelMessagesTypeAdapter.validate_python(latest_conversation_messages)
            previous_messages = latest_conversation_messages[-MAX_CHAT_MESSAGES:]
            parsed_messages = []
            for message in previous_messages:
                new_parts = []
                for part in message["parts"]:
                    # remove tool_call
                    if "tool-call" in part["part_kind"]:
                        print("removing tool call", part)
                        continue
                    new_parts.append(part)
                message["parts"] = new_parts

                if message["parts"] == []:
                    continue
                if "timestamp" not in message:
                    continue
                try:
                    # check if timestamp is already a datetime object
                    if isinstance(message["timestamp"], datetime):
                        continue
                    # Adjust format string if necessary
                    timestamp_obj = datetime.strptime(
                        message["timestamp"], "%a, %d %b %Y %H:%M:%S GMT"
                    )
                    message["timestamp"] = timestamp_obj
                    parsed_messages.append(message)
                except ValueError:
                    # Handle parsing errors (optional)
                    print(f"Failed to parse timestamp for message: {message}")
                    pass  # Skip the message if parsing fails

            previous_messages = parsed_messages

            print("previous messages: ", previous_messages)
            # previous_messages = ModelMessagesTypeAdapter.validate_python(
            #     previous_messages
            # )

        prompt = f"""Given the following document(s), answer the following question. Return the result as nicely formatted html div."""
        debug(max_context_length)
        if len(full_text) > max_context_length:
            prompt += f"""
            Do not include the question in your response.
            {full_text}
            """
            answer = chat_agent.run_sync(
                prompt,
                message_history=previous_messages,
                )
            debug("llmchat", answer)

        else:
            prompt += f"""
        \nDocument(s): {[doc.path for doc in documents]}\n
        Question: {question}
        """
            debug("Rag chat", prompt)
            deps = RagDeps(doc_manager=DocumentManager(), user_id=user_id or "0", documents=documents)
            answer = rag_agent.run_sync(
                prompt,
                deps=deps,
                message_history=previous_messages,
            )
        # print("answer: ", answer.new_messages_json())
        # Save new messages
        # AgentHistory.save_messages(user_id, answer.new_messages_json())

        # remove None
        chat_history = json.loads(answer.new_messages_json())
        debug(chat_history)
        cache.update(cache_key, llm_string, chat_history)
        # if session is not None:
        #     new_chat_history = latest_conversation_messages + answer.new_messages()
        #     # save the latest max messages
        #     session["chat_history"] = new_chat_history

        return dict(
            question=question,
            answer=self.format_answer(answer.data),
            formatted_answer=self.format_answer(answer.data),
        )

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
