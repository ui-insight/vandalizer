import os

from app import app
from dotenv import load_dotenv
from langfuse.decorators import langfuse_context
import logging
from dotenv import load_dotenv
from contextvars import ContextVar
import nest_asyncio
import asyncio
import threading

load_dotenv()


def setup_event_loop():
    """Setup event loop for the current thread"""
    # Get thread id for debugging
    thread_id = threading.current_thread().ident
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    nest_asyncio.apply()
    return loop


# Set up the event loop for the current thread
setup_event_loop()

if os.environ.get("LOGFIRE") == "true":
    import logfire

    logfire.configure()

langfuse_enabled = os.environ.get("LOG_ENABLED", "false").lower() == "true"

# app.logger.info(f"Langfuse enabled: {langfuse_enabled}")
# app.logger.info(f"Langfuse host: {os.environ.get('NEXTAUTH_URL')}")

# Configure the Langfuse client
langfuse_context.configure(
    enabled=langfuse_enabled,
    secret_key=os.environ.get("LANGFUSE_SECRET_KEY"),
    public_key=os.environ.get("LANGFUSE_PUBLIC_KEY"),
    host=os.environ.get("NEXTAUTH_URL"),
)

load_dotenv()


# ----------------------------------------
# launch
# ----------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, ssl_context=("certs/cert.pem", "certs/key.pem"))
