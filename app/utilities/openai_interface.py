import json
import os

import openai
from devtools import debug
from pydantic_ai.messages import ModelMessagesTypeAdapter

from app.utilities.llm import ChatLM

import asyncio

from app.models import (
    MAX_CHAT_MESSAGES,
)
from app.utilities.agents import RagDeps, create_chat_agent, create_rag_agent
from app.utilities.async_utilities import class_method_event_loop_decorator
from app.utilities.config import settings
from app.utilities.document_manager import DocumentManager
from app.utilities.document_readers import extract_text_from_doc
from app.utilities.llm import ChatLM, remove_code_markers
from app.utilities.redis_cache import RedisCache
from app.models import ModelConfig

from dotenv import load_dotenv


load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")

# 2h
ttl = 60 * 60 * 1
cache = RedisCache(redis_url=f"redis://{REDIS_HOST}:6379/0", ttl=ttl)

# TODO remove the formatting of the answer from the OpenAIInterface class
# it is taking so much time to execute the call


# TODO we might need to rename the class
class OpenAIInterface:
    loaded_doc = ""

    def load_document(self, document_path) -> None:
        self.loaded_doc = extract_text_from_doc(document_path)

    # @observe()
    def ask_question_to_loaded_document(self, item):
        openai.api_key = os.getenv("OPENAI_API_KEY")
        prompt = ""
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
            prompt = (
                """Given the following document, answer the following question. Return the result as nicely formatted html.:\nQuestion:\n"""
                + item.searchphrase
                + "\n\nDocument:\n"
                + self.loaded_doc
            )

        model = settings.base_model
        model_config = ModelConfig.objects(user_id=item.user_id).first()
        if model_config is not None:
            model = model_config.name
        chat_agent = create_chat_agent(model)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(
            chat_agent.run(
                messages=[{"role": "user", "content": prompt}],
            )
        )

        return result.output

    def get_cache_messages(user_id, docs_ids_string, session=None):
        cache_key = f"chat_history_{user_id}_{docs_ids_string}"
        llm_string = "pydantic_model:openai:gpt-4o"
        previous_messages = []
        latest_conversation_messages = []
        debug(session)
        if session is not None:
            # latest_conversation_messages = session.get("chat_history", [])
            cache_result = cache.lookup(cache_key, llm_string)
            if cache_result is not None:
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
                        continue
                    new_parts.append(part)
                message["parts"] = new_parts

                if message["parts"] == []:
                    continue
                # remove timestamp if exists in message
                if "timestamp" in message:
                    del message["timestamp"]

            previous_messages = parsed_messages

        return previous_messages, cache_key, llm_string

    def get_full_text(documents, previous_messages):
        full_text = ""
        for document in documents:
            absolute_path = document.absolute_path
            document_content_in_previous_messages = False
            for message in previous_messages:
                for part in message["parts"]:
                    if f"Document: {document.title}" in part["content"]:
                        document_content_in_previous_messages = True
                        break
            if document_content_in_previous_messages:
                full_text += f"\n\nDocument: {document.title} "
                continue
            full_text += (
                "\n\nDocument: "
                + extract_text_from_doc(doc=document, doc_path=absolute_path)
                + " "
            )
        return full_text

    @class_method_event_loop_decorator()
    def ask_question_to_documents(
        self,
        model,
        root_path,
        documents,
        question,
        session=None,
        user_id=None,
        default_docs=None,
    ):
        if default_docs is None:
            default_docs = []
        default_docs = list(default_docs)
        documents = list(documents)
        docs = default_docs + documents

        openai.api_key = os.getenv("OPENAI_API_KEY")

        docs_ids_string = "_".join([str(doc.id) for doc in docs])

        prompt = """Given the following document(s), answer the question. Return the result as nicely formatted html div. Do not include the question in your response."""

        previous_messages, cache_key, llm_string = OpenAIInterface.get_cache_messages(
            user_id=user_id,
            docs_ids_string=docs_ids_string,
            session=session,
        )

        max_context_length = settings.max_context_length

        full_text = OpenAIInterface.get_full_text(documents, previous_messages)
        debug(max_context_length)
        debug(len(full_text))

        answer = None

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        if len(full_text) < max_context_length:
            prompt += f"""Question: {question} Document: {full_text}"""
            try:
                chat_agent = create_chat_agent(model)
                answer = loop.run_until_complete(
                    chat_agent.run(
                        prompt,
                        message_history=previous_messages,
                    )
                )

                debug("llmchat", answer)
            except Exception as e:
                debug(f"Error during LLM chat: {e}")
        else:
            prompt += f"""\nDocument(s): {[doc.uuid for doc in documents]}\n Question: {question}"""
            debug("Rag chat", prompt)
            try:
                rag_agent = create_rag_agent(model)
                deps = RagDeps(
                    doc_manager=DocumentManager(),
                    user_id=user_id or "0",
                    documents=documents,
                )
                answer = loop.run_until_complete(
                    rag_agent.run_sync(
                        prompt,
                        deps=deps,
                        message_history=previous_messages,
                    )
                )
            except Exception as e:
                debug("Error in rag chat", e)

        debug(answer)
        chat_history = json.loads(answer.new_messages_json())
        cache.update(cache_key, llm_string, chat_history)

        return {
            "question": question,
            "answer": remove_code_markers(answer.output),
            "formatted_answer": remove_code_markers(answer.output),
        }
