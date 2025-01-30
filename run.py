import os

from app import app
from dotenv import load_dotenv
from langfuse.decorators import langfuse_context
import logging
from dotenv import load_dotenv

load_dotenv()

import nest_asyncio

nest_asyncio.apply()

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
    # if "dev" in hostname, then it is a dev server
    if "prod" in os.uname().nodename:
        os.environ["APP_ENV"] = "prod"
    elif "dev" in os.uname().nodename:
        os.environ["APP_ENV"] = "dev_prod"
    else:
        # local dev for testing
        os.environ["APP_ENV"] = "dev"

    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port)
