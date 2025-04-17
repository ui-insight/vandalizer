# Document Review with LLM Models

A Flask-based application for document review and processing using large language models.

Wee!

## Features

- Document upload and storage
- AI-powered document analysis and grading
- Background task processing with Celery
- Azure-based OAuth authentication
- Rollbar error tracking
- Email notifications

## Deployment

Before deploying to each environment, update the configuration by:

1. Setting `FLASK_ENV` to `Development`, `Testing`, or `Production`.
2. Restarting the Flask and Celery services. Restart Celery by running ./run_celery.sh


## Installation

### Prerequisites

- Python 3.9+
- Redis server (for Celery broker and backend)
- MongoDB server
- Mail server accessible by SMTP

### Installation

1. Clone the repository:

   ```bash
   git clone git@github.com:your-org/your-repo.git
   cd your-repo
   ```

2. Create and activate a virtual environment:

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env` and fill in the required secrets.

## Necessary Secrets

The following environment variables must be set:

- `SECRET_KEY`: Flask secret key
- `SECURITY_PASSWORD_SALT`: Salt for security-related operations
- `CLIENT_ID`, `CLIENT_SECRET`, `TENANT_NAME`: Azure OAuth credentials
- `MONGODB_SETTINGS__DB`: Mongo database name (e.g. `osp_dev`, `osp_prod`, etc.)
- `MONGODB_SETTINGS__HOST`, `MONGODB_SETTINGS__PORT`: Mongo host and port if not default
- `REDIS_BROKER_URL`, `REDIS_RESULT_BACKEND`: Redis connection URLs for Celery (optional, override defaults)
- `ROLLBAR_ACCESS_TOKEN`: Rollbar API token
- `MAIL_SERVER`, `MAIL_PORT`, `MAIL_DEFAULT_SENDER`: Mail server settings if different from defaults

## Testing

We have End-to-End tests written in pytest and Selenium.

- To run against the dev server:

  ```bash
  tox run
  ```

  This uses `https://vandalizer-dev.nkn.uidaho.edu` and runs in a headless browser.

- To run locally:

  ```bash
  pytest
  ```




