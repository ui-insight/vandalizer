import asyncio
import json
import logging
import os
import uuid

import openai
from devtools import debug
from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
)

from app.models import (
    MAX_CHAT_MESSAGES,
    UserModelConfig,
    ChatConversation,
    ChatRole,
)
from app.utilities.agents import RagDeps, create_chat_agent, create_rag_agent
from app.utilities.config import settings
from app.utilities.document_manager import DocumentManager
from app.utilities.document_readers import extract_text_from_doc
from app.utilities.llm_helpers import (
    remove_base64_images,
    remove_code_markers,
    remove_xml_content,
)
from app.utilities.web_utils import URLContentFetcher
from app.utilities.redis_cache import RedisCache

load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")

# 2h
ttl = 60 * 60 * 1
cache = RedisCache(redis_url=f"redis://{REDIS_HOST}:6379/0", ttl=ttl)

# TODO remove the formatting of the answer from the OpenAIInterface class
# it is taking so much time to execute the call

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
                """Given the following document, and the attached additional context, answer the following question. Return the result as nicely formatted markdown.\nQuestion:\n"""
                + item.searchphrase
            )

            for block in item.text_blocks:
                prompt += "\n\nContext:\n" + block

            prompt += "\n\nDocument:\n" + self.loaded_doc
            # print(prompt)
        else:
            prompt = (
                """Given the following document, answer the following question. Return the result as nicely formatted markdown.:\nQuestion:\n"""
                + item.searchphrase
                + "\n\nDocument:\n"
                + self.loaded_doc
            )

        model = settings.base_model
        model_config = UserModelConfig.objects(user_id=item.user_id).first()
        if model_config is not None:
            model = model_config.name
        chat_agent = create_chat_agent(model)
        result = chat_agent.run_sync(
            messages=[{"role": "user", "content": prompt}],
        )

        return result.output

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

    def _prepare_chat(
        self,
        model,
        root_path,
        documents,
        question,
        previous_messages=[],
        conversation_uuid=None,
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

        prompt = """Given the following document(s), answer the question. Return the result as nicely formatted markdown. Do not include the question in your response. At the end include a very short suggestion of next questions to ask or next steps the user might do with the documents."""

        if len(docs) == 0:
            prompt = "Answer the question. Return the result as nicely formatted markdown. Do not include the question in your response."

        debug(user_id)

        max_context_length = settings.max_context_length

        full_text = OpenAIInterface.get_full_text(documents, previous_messages)
        # remove base64 images from full_text
        full_text = remove_base64_images(full_text)

        agent = None
        if len(full_text) < max_context_length:
            prompt += f"""\nQuestion: {question}\n{full_text}"""
            agent = create_chat_agent(model)
        else:
            prompt += f"""\nDocument(s): {[doc.uuid for doc in documents]}\n Question: {question}"""
            agent = create_rag_agent(model)
            debug("Rag chat", prompt)

        return dict(
            agent=agent,
            prompt=prompt,
            user_id=user_id,
            full_text=full_text,
        )

    def ask_question_to_documents(
        self,
        model,
        root_path,
        documents,
        question,
        previous_messages=[],
        conversation_uuid=None,
        session=None,
        user_id=None,
        default_docs=None,
    ):
        prepared_data = self._prepare_chat(
            model=model,
            root_path=root_path,
            documents=documents,
            question=question,
            previous_messages=previous_messages,
            session=session,
            user_id=user_id,
            default_docs=default_docs,
        )
        agent = prepared_data["agent"]
        prompt = prepared_data["prompt"]
        user_id = prepared_data["user_id"]
        full_text = prepared_data["full_text"]

        answer = None

        try:
            if len(full_text) >= settings.max_context_length:
                deps = RagDeps(
                    doc_manager=DocumentManager(),
                    user_id=user_id or "0",
                    documents=documents,
                )
                answer = agent.run_sync(
                    prompt,
                    deps=deps,
                    message_history=previous_messages,
                )
            else:
                answer = agent.run_sync(
                    prompt,
                    message_history=previous_messages,
                )
        except Exception as e:
            debug("Error in chat", e)

        if hasattr(answer, "output"):
            answer = answer.output
        else:
            answer = str(answer)

        answer = remove_xml_content(answer, "think")
        answer = remove_code_markers(answer)

        return {"question": question, "answer": answer, "formatted_answer": answer}

    def ask_question_to_documents_stream(
        self,
        model,
        root_path,
        documents,
        question,
        previous_messages=[],
        conversation_uuid=None,
        session=None,
        user_id=None,
        default_docs=None,
    ):
        prepared_data = self._prepare_chat(
            model=model,
            root_path=root_path,
            documents=documents,
            question=question,
            session=session,
            user_id=user_id,
            default_docs=default_docs,
        )
        agent = prepared_data["agent"]
        prompt = prepared_data["prompt"]

        conversation = ChatConversation.objects(
            uuid=conversation_uuid,
            user_id=user_id,
        ).first()
        if conversation:
            # Include URL attachments in the context
            url_context = ""
            for url_attachment in conversation.url_attachments:
                if url_attachment.content:
                    url_context += f"\n\nWeb Content from {url_attachment.url}:\n{url_attachment.content[:10000]}\n"

        # Add URL context to the prompt if it exists
        if url_context:
            prompt += f"\n\nAdditional context from web links:{url_context}"

        # fetcher = URLContentFetcher(max_content_length=30000)
        # result = fetcher.process_chat_input(question)
        # print(result)
        # if isinstance(result, str):
        #     # If result is a string, add it directly
        #     prompt += result
        # elif isinstance(result, (list, tuple)):
        #     # If result is a list/tuple, join with newlines
        #     prompt += "\n".join(str(item) for item in result)
        # else:
        #     # Fallback: convert to string
        #     prompt += str(result)
        print("Final prompt to the model:")
        print(prompt)

        full_response = []

        async def streamer():
            async with agent.iter(prompt, message_history=previous_messages) as agent_run:
                async for node in agent_run:
                    if Agent.is_model_request_node(node):
                        async with node.stream(agent_run.ctx) as stream:
                            async for event in stream:
                                if isinstance(event, PartStartEvent):
                                    if isinstance(event.part, TextPart):
                                        # remove code markers
                                        # content = remove_code_markers(event.part.content)
                                        content = event.part.content
                                        full_response.append(content)
                                        yield (
                                            json.dumps(
                                                dict(kind="text", content=content)
                                            )
                                            + "\n"
                                        )
                                    elif isinstance(event.part, ThinkingPart):
                                        yield (
                                            json.dumps(
                                                dict(
                                                    kind="thinking",
                                                    content=event.part.content,
                                                )
                                            )
                                            + "\n"
                                        )
                                if isinstance(event, PartDeltaEvent):
                                    if isinstance(event.delta, TextPartDelta):
                                        # remove code markers
                                        # content = remove_code_markers(event.delta.content_delta)  # noqa: E501
                                        content = event.delta.content_delta
                                        full_response.append(content)
                                        yield (
                                            json.dumps(
                                                dict(kind="text", content=content)
                                            )
                                            + "\n"
                                        )
                                    elif isinstance(event.delta, ThinkingPartDelta):
                                        yield (
                                            json.dumps(
                                                dict(
                                                    kind="thinking",
                                                    content=event.delta.content_delta,
                                                )
                                            )
                                            + "\n"
                                        )
                    # elif Agent.is_call_tools_node(node):

            if full_response:
                assistant_message = ''.join(full_response)
                conversation.add_message(ChatRole.ASSISTANT, assistant_message)


        # Bridge the async generator to a sync iterator for Flask
        def sync_streamer():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            agen = streamer().__aiter__()

            while True:
                try:
                    chunk = loop.run_until_complete(agen.__anext__())
                    yield chunk
                except StopAsyncIteration:
                    break
            loop.close()

        return sync_streamer()
