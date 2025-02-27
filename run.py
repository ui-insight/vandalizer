import os

from app import app
from dotenv import load_dotenv
import logging
from contextvars import ContextVar
import nest_asyncio
import asyncio
import threading
from devtools import debug

load_dotenv()

if os.environ.get("LOGFIRE") == "true":
    import logfire

    logfire.configure()

langfuse_enabled = os.environ.get("LOG_ENABLED", "false").lower() == "true"

# app.logger.info(f"Langfuse enabled: {langfuse_enabled}")
# app.logger.info(f"Langfuse host: {os.environ.get('NEXTAUTH_URL')}")

# if langfuse_enabled:
# from langfuse.decorators import langfuse_context

# # Configure the Langfuse client
# langfuse_context.configure(
#     enabled=langfuse_enabled,
#     secret_key=os.environ.get("LANGFUSE_SECRET_KEY"),
#     public_key=os.environ.get("LANGFUSE_PUBLIC_KEY"),
#     host=os.environ.get("NEXTAUTH_URL"),
# )


# ----------------------------------------
# launch
# ----------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, ssl_context=("certs/cert.pem", "certs/key.pem"))
