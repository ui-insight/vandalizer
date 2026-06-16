import json
import logging
import re
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.dependencies import get_current_user
from app.models.system_config import SystemConfig
from app.models.user import User
from app.rate_limit import limiter
from app.services.config_service import get_user_model_name
from app.services.llm_service import create_chat_agent
from app.services.metering import metered_async

logger = logging.getLogger(__name__)

router = APIRouter()


class AppGenerateRequest(BaseModel):
    prompt: str
    system_prompt: Optional[str] = None
    schema_def: Optional[Dict[str, Any]] = None
    model: Optional[str] = None


@router.post("/generate")
@limiter.limit("30/minute")
async def app_generate(
    request: Request,
    body: AppGenerateRequest,
    user: User = Depends(get_current_user),
):
    """
    Universal LLM connector for side-loaded applications.

    Handles standard text generation and strict JSON schema
    enforcement across all model providers.
    """
    try:
        # 1. Resolve Model
        model_name = body.model or await get_user_model_name(user.user_id)

        cfg = await SystemConfig.get_config()
        sys_config_doc = cfg.model_dump() if cfg else {}

        # 2. Construct System Prompt
        sys_prompt = body.system_prompt or "You are a helpful assistant."

        # If the app requested structured JSON, append strict instructions
        if body.schema_def:
            sys_prompt += (
                "\n\nCRITICAL INSTRUCTION: You must output ONLY valid, "
                "raw JSON that strictly conforms to this JSON Schema:\n"
                f"{json.dumps(body.schema_def)}\n"
                "Do not include Markdown formatting. "
                "Do not use ```json wrappers. "
                "Do not include any conversational text before or after "
                "the JSON."
            )

        # 3. Initialize Agent
        agent = create_chat_agent(
            model_name,
            system_prompt=sys_prompt,
            thinking_override=False,
            system_config_doc=sys_config_doc,
        )

        # 4. Execute with Metering
        team_id = (
            str(user.current_team)
            if getattr(user, "current_team", None)
            else None
        )

        async with metered_async(
            "app_connector_generate",
            user_id=user.user_id,
            team_id=team_id,
        ):
            result = await agent.run(body.prompt)

        # 5. Extract Output
        output_text = (
            result.output
            if hasattr(result, "output")
            else str(result.data)
        )

        # 6. Robustly Clean Conversational Text & Markdown
        if body.schema_def:
            # Try to extract JSON from markdown code blocks first
            match = re.search(
                r"```(?:json)?\s*(.*?)\s*```",
                output_text,
                re.DOTALL,
            )

            if match:
                output_text = match.group(1)
            else:
                # Fallback: Find the first { and last }
                # (or [ and ])
                start_dict = output_text.find("{")
                end_dict = output_text.rfind("}")

                start_list = output_text.find("[")
                end_list = output_text.rfind("]")

                # Determine whether the JSON is an object or array
                if (
                    start_dict != -1
                    and end_dict != -1
                    and (
                        start_list == -1
                        or start_dict < start_list
                    )
                ):
                    output_text = output_text[
                        start_dict : end_dict + 1
                    ]

                elif start_list != -1 and end_list != -1:
                    output_text = output_text[
                        start_list : end_list + 1
                    ]

            output_text = output_text.strip()

            # Verify it's actually parsable before returning
            try:
                parsed_json = json.loads(output_text)

                return {
                    "data": parsed_json,
                    "format": "json",
                }

            except json.JSONDecodeError:
                logger.error(
                    "App Connector JSON Parse Error. "
                    f"Cleaned output: {output_text}"
                )

                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="The model failed to return valid JSON.",
                )

        return {
            "data": output_text.strip(),
            "format": "text",
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception("App Connector Error")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred.",
        )
