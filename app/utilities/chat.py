#!/usr/bin/env python3

from datetime import datetime

from devtools import debug
from pydantic_ai.messages import ModelMessagesTypeAdapter

from app.utilities.agents import create_chat_agent
from app.utilities.redis_cache import RedisCache
from app.utilities.config import settings

# 2h
ttl = 60 * 60 * 1
cache = RedisCache(redis_url="redis://localhost:6379", ttl=ttl)

from app.models import MAX_CHAT_MESSAGES
from app.models import ModelConfig


def chat_with_prompt(prompt: str, user_id=0) -> str:
    cache_key = f"chat_office_{user_id}"
    llm_string = "pydantic_model:openai:gpt-4o"
    previous_messages = []
    latest_conversation_messages = []
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
                message["timestamp"], "%a, %d %b %Y %H:%M:%S GMT",
            )
            message["timestamp"] = timestamp_obj
            parsed_messages.append(message)
        except ValueError:
            # Handle parsing errors (optional)
            pass
            # Skip the message if parsing fails

    previous_messages = parsed_messages
    debug(previous_messages)

    model_config = ModelConfig.objects(user_id=user_id).first()
    if model_config is not None:
        # Use the model_config to set the model
        model = model_config.name
    else:
        # Fallback to a default model if no config is found
        model = settings.base_model

    chat_agent=create_chat_agent(
        model=model,
        user_id=user_id,
        cache=cache,
    )

    answer = chat_agent.run_sync(
        prompt,
        message_history=previous_messages,
    )
    return answer.data
