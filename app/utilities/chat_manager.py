import asyncio
import json
import logging
import os

import openai
from devtools import debug
from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.messages import (
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
)

from app.models import (
    ChatConversation,
    ChatRole,
    UserModelConfig,
    ActivityEvent,
    ActivityStatus,
)

from app.utilities.analytics_helper import (
    activity_finish,
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
from app.utilities.redis_cache import RedisCache

load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")

SYSTEM_PROMPT = """You are a precise, concise assistant.
Output: well-structured Markdown with clear headings and bullets.
Do NOT restate the question. If info is missing, say so briefly and proceed best-effort.
Citations: refer to provided context naturally; no raw links unless asked.
When given documents, prioritize: (1) relevance, (2) recency, (3) non-duplication.

Next-Step Guidance
- Only ask clarifying questions when strictly necessary to proceed or prevent errors.
- End with one short, action-oriented “next step?” line only when appropriate.
- The next step must be tailored, concrete, valuable, and ≤ 16 words, phrased as a question.
- If confidence is low, prefer a quick validation step.
- If an action depends on missing input, ask for the single most critical item.
- You may offer at most one lightweight alternative in parentheses.

Allowed forms (pick exactly one):
1) "Want me to <do X>?"
2) "Next step: <single concrete action>?"
3) "Should we <validate/compare/prioritize> next?"
4) "Do you want <A> (or <B>)?"

Anti-patterns (never do):
- Don’t restate your whole answer in the next step.
- Don’t propose multi-step plans; keep it to one step.
- Don’t ask vague things like "Need anything else?"
"""

# 2h
ttl = 60 * 60 * 1
cache = RedisCache(redis_url=f"redis://{REDIS_HOST}:6379/0", ttl=ttl)

# TODO remove the formatting of the answer from the ChatManager class
# it is taking so much time to execute the call

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ChatManager:
    loaded_doc = ""

    def load_document(self, document_path) -> None:
        self.loaded_doc = extract_text_from_doc(document_path)

    # @observe()
    def ask_question_to_loaded_document(self, item):
        openai.api_key = os.getenv("OPENAI_API_KEY")
        prompt = ""
        if len(item.text_blocks) > 0:
            prompt = (
                """Given the following document(s), and the attached additional context, answer the following query. Return the result as nicely formatted markdown.\n## Query:\n"""
                + item.searchphrase
            )

            for block in item.text_blocks:
                prompt += "\n\n# Context:\n" + block

            prompt += "\n\n# Document(s):\n" + self.loaded_doc
            # print(prompt)
        else:
            prompt = (
                """Given the following document(s), answer the following query. Return the result as nicely formatted markdown.:\n# Query:\n"""
                + item.searchphrase
                + "\n\n# Document(s):\n"
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
                full_text += f"\n\n## Document: {document.title}\n "
                continue
            full_text += (
                "\n\n## Document:\n"
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
        prompt = ""

        if len(docs) > 0:
            prompt = "You are given the following document(s). "

        prompt += """Answer the query clearly and concisely, formatting your response in well-structured markdown. 
Do not restate or include the original query in your answer. 
At the end of your response, provide a short, relevant suggestion for a logical next step related to the query, and phrase it as a question asking if the user would like to do that specific suggestion."""

        debug(user_id)

        max_context_length = settings.max_context_length

        full_text = ChatManager.get_full_text(documents, previous_messages)
        # remove base64 images from full_text
        full_text = remove_base64_images(full_text)

        agent = None
        if len(full_text) < max_context_length:
            prompt += f"""\n\n# Query: {question}\n\n # Context: \n{full_text}"""
            agent = create_chat_agent(model)
        else:
            prompt += f"""\n\n# Document(s): {[doc.uuid for doc in documents]}\n""" 
            agent = create_rag_agent(model)
            debug("Rag chat", prompt)

        return {
            "agent": agent,
            "prompt": prompt,
            "previous_messages": previous_messages,
            "user_id": user_id,
            "full_text": full_text,
        }

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
        debug(user_id)
        debug(conversation_uuid)
        debug(conversation)

        # Build attachment context FIRST
        attachment_context = ""
        if conversation:
            # Add URL attachments to context
            if conversation.url_attachments:
                for url_attachment in conversation.url_attachments:
                    if url_attachment.content:
                        attachment_context += f"\n\n## Web Content: {url_attachment.title}\nSource: {url_attachment.url}\n\n{url_attachment.content[:10000]}\n"

            # Add file attachments to context
            if conversation.file_attachments:
                for file_attachment in conversation.file_attachments:
                    if file_attachment.content:
                        attachment_context += f"\n\n## Document: {file_attachment.filename}\n\n{file_attachment.content[:10000]}\n"

            # NOW load previous messages (which won't include the full content)
            previous_messages = conversation.to_model_messages()
            debug(previous_messages)

        # Add attachment context to prompt
        if attachment_context:
            prompt = f"{prompt}\n\n---\n# Attached Context:{attachment_context}\n---\n"
    
        print("Final prompt to the model:")
        print(prompt)

        full_response = []

        async def streamer():
            async with agent.iter(
                prompt, message_history=previous_messages
            ) as agent_run:
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
                                                {"kind": "text", "content": content}
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
                                                {
                                                    "kind": "thinking",
                                                    "content": event.delta.content_delta,
                                                }
                                            )
                                            + "\n"
                                        )
                    # elif Agent.is_call_tools_node(node):
                     
                if agent_run.result:
                    usage = agent_run.result.usage()
                    debug(usage)
                    debug(agent_run)
                    assistant_message = agent_run.result.output
                    conversation.add_message(ChatRole.ASSISTANT, assistant_message)
                    conversation.reload()
                    activity = ActivityEvent.objects(
                        user_id=user_id,
                        conversation_id=conversation.uuid,
                    ).first()
                    if activity:
                        activity.message_count = len(conversation.messages)
                        activity.status = ActivityStatus.COMPLETED.value

                        activity.tokens_input = usage.request_tokens
                        activity.tokens_output = usage.response_tokens
                        activity.total_tokens = usage.request_tokens + usage.response_tokens
                        activity.message_count = len(conversation.messages)
                        activity.documents_touched = len(documents)
                        activity_finish(activity)

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
