import os
from app import app


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
