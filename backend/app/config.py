from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    mongo_host: str = "mongodb://localhost:27017/"
    mongo_db: str = "vandalizer"
    redis_host: str = "localhost"
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 30
    jwt_refresh_expire_days: int = 60
    upload_dir: str = "../app/static/uploads"
    frontend_url: str = "http://localhost:5173"
    environment: str = "development"
    # Explicit override for the Secure attribute on auth/CSRF cookies. Leave
    # unset to derive it from environment + frontend_url (see
    # use_secure_cookies): Secure in production, EXCEPT when the deployment is
    # served over plain http:// — a browser silently drops Secure cookies on
    # HTTP, so login would "succeed" and every following request would 401.
    cookie_secure: bool | None = None
    # Human-readable name for THIS deployment, shown in the UI version footer so
    # users can tell environments apart (e.g. "U of I Prod", "National Trial Prod").
    # `environment` alone can't: both prods report "production". Falls back to
    # `environment` when unset.
    deployment_label: str = ""
    # IANA timezone for Celery beat crontab schedules (daily digests, engagement
    # emails, retention jobs). Celery defaults to UTC when unset, which made
    # "daily at 10am" emails land at 3am Pacific. Default matches the primary
    # deployment (Moscow, ID).
    celery_timezone: str = "America/Los_Angeles"
    insight_endpoint: str = ""
    chromadb_persist_dir: str = "../app/static/db"
    # If set (e.g. "chromadb:8000"), connect to a Chroma server via HttpClient.
    # Required when multiple processes (FastAPI workers + Celery) share Chroma —
    # PersistentClient is not process-safe for concurrent writers.
    chromadb_host: str = ""
    max_upload_size_mb: int = 500

    # Observability
    sentry_dsn: str = ""
    log_format: str = "json"  # "json" for structured logging, "text" for human-readable

    # Email provider: "smtp" or "resend"
    email_provider: str = "smtp"

    # SMTP email settings
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = False  # Implicit TLS (port 465)
    smtp_start_tls: bool = True  # STARTTLS upgrade (port 587)
    smtp_from_email: str = ""
    smtp_from_name: str = "Vandalizer"

    # Resend email settings (used when email_provider=resend)
    resend_api_key: str = ""
    resend_from_email: str = ""
    resend_from_name: str = "Vandalizer"

    # Encryption key for sensitive config values (API keys) stored in MongoDB.
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    config_encryption_key: str = ""

    # File storage backend ("local" or "s3")
    storage_backend: str = "local"
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_endpoint_url: str | None = None

    # Trial / demo system (disabled by default for self-hosters)
    enable_trial_system: bool = False

    # Upstream update check — hits api.github.com once per hour (cached in Redis)
    # to surface an "update available" banner to admins. Set to True to opt out
    # for air-gapped or privacy-strict deployments.
    disable_update_check: bool = False

    # Anonymous deployment telemetry — OPT-IN, OFF by default.
    #
    # When enabled, a once-daily heartbeat lets the maintainers see how many
    # deployments exist and roughly how heavily they're used. It sends ONLY:
    #   - a stable random instance UUID (generated locally, no link to identity)
    #   - the running version and coarse environment (production / non-production)
    #   - usage as COARSE BUCKETS ("11-50 users", not exact counts)
    # It NEVER sends document content, filenames, titles, user identities,
    # emails, API keys, team names, or any free text.
    #
    # Trust guarantees baked into the implementation:
    #   - The single master gate is enablement (off by default); nothing is sent
    #     until an admin opts in (via setup.sh or the in-app banner).
    #   - Every payload is logged locally (telemetry_log_payload) so an admin can
    #     read exactly what was sent.
    #   - Self-hosters can point telemetry_endpoint at their OWN collector.
    #
    # telemetry_enabled here is only the INITIAL/default state. The durable
    # runtime decision lives in SystemConfig.telemetry_config (DB) once an admin
    # decides via the in-app banner — so it can be toggled without an env edit or
    # restart. See telemetry_service.resolve_runtime_config for the precedence.
    telemetry_enabled: bool = False
    # Defaulted so an admin who enables via the in-app banner on an existing
    # install (whose .env predates telemetry) still has somewhere to send to.
    # Override to self-host the collector, or blank it to hard-disable sending.
    telemetry_endpoint: str = "https://vandalizer.nkn.uidaho.edu/api/telemetry/heartbeat"
    telemetry_log_payload: bool = True
    # Set true by setup.sh once it has asked about telemetry (yes OR no), so the
    # in-app banner never re-asks someone the installer already prompted.
    telemetry_prompted: bool = False

    # Optional SECOND tier on top of the anonymous heartbeat: voluntary identity.
    # If an admin chooses to fill these in (typically at deploy time via
    # setup.sh), the heartbeat additionally reports who the deployment is, so the
    # maintainers can see *named* adoption rather than just counts. Empty by
    # default — a blank organization keeps the heartbeat fully anonymous (the
    # identity block is omitted from the payload entirely). NEVER auto-derived
    # from email domains, IPs, or licenses; self-declared only.
    telemetry_organization: str = ""
    telemetry_contact_email: str = ""

    # RECEIVER role — turns THIS deployment into the fleet telemetry collector.
    # Off by default, so every other deployment running this same codebase keeps
    # the ingest route and the admin analytics screen completely hidden. Only the
    # maintainers' own instance (the heartbeat's default endpoint) sets this True.
    telemetry_collector_enabled: bool = False

    # Web fetcher — controls Playwright fallback for JS-rendered pages.
    # When True (default), pages whose static HTML yields too little text are
    # re-fetched in a headless Chromium so client-rendered SPAs (Next.js,
    # Nuxt, etc.) produce usable content for chat / workflow / KB ingestion.
    web_fetcher_browser_enabled: bool = True
    web_fetcher_min_chars: int = 500
    # Cap on the *extracted* main-content text kept from a page.
    web_fetcher_max_chars: int = 500_000
    # Cap on the *raw HTML* parsed before extraction. This must be much larger
    # than web_fetcher_max_chars: HTML markup (nav, inline styles, deeply nested
    # tables, scripts) dwarfs the readable text, so long .gov/.edu pages routinely
    # exceed 500 KB of HTML well before the document body ends. Capping raw HTML at
    # the *text* limit silently drops the tail of the page before it is ever
    # parsed (e.g. a reg page cut off mid-document, losing later subparts).
    web_fetcher_max_html_chars: int = 8_000_000
    web_fetcher_timeout_seconds: int = 30

    # Minimum characters of extracted content for an auto-discovered crawl page
    # to be kept as a KB source. Pages below it are site navigation (Home,
    # Topics, Agencies) — still followed for their links, never embedded. Does
    # not apply to a URL the user pasted themselves; that is always kept.
    kb_crawl_min_content_chars: int = 1200

    # Per-request read timeout (seconds) for the dedicated httpx client used by
    # workflow LLM calls. Reasoning models (e.g. gpt-oss) can think for a while
    # over a large document before emitting the first token, so this is set
    # generously above httpx's 5s default.
    workflow_llm_timeout_seconds: int = 120

    # A document whose extracted text has a non-letter ratio above this is
    # treated as a garbled extraction (broken font encoding / CID-mangled text
    # layer) and chat over it carries a low-quality warning. Clean extractions
    # measure ≤0.01 and garbled ones ~0.5, so anywhere in between works; 0.25
    # leaves wide margin on both sides and tolerates notation-heavy documents.
    extraction_max_nonletter_ratio: float = 0.25

    @model_validator(mode="after")
    def _resolve_paths(self) -> "Settings":
        # Resolve relative paths against the backend directory (parent of app/)
        # so Celery workers and FastAPI resolve identically regardless of cwd.
        backend_dir = Path(__file__).resolve().parent.parent
        upload = Path(self.upload_dir)
        chroma = Path(self.chromadb_persist_dir)
        self.upload_dir = str(upload if upload.is_absolute() else (backend_dir / upload).resolve())
        self.chromadb_persist_dir = str(chroma if chroma.is_absolute() else (backend_dir / chroma).resolve())
        # Ensure directories exist on startup
        Path(self.upload_dir).mkdir(parents=True, exist_ok=True)
        Path(self.chromadb_persist_dir).mkdir(parents=True, exist_ok=True)
        return self

    @model_validator(mode="after")
    def _check_jwt_secret(self) -> "Settings":
        if self.jwt_secret_key == "change-me" and self.environment != "development":
            raise ValueError(
                "jwt_secret_key must be changed from the default 'change-me' "
                "in non-development environments. Generate one with: "
                "python -c \"import secrets; print(secrets.token_urlsafe(64))\""
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def use_secure_cookies(self) -> bool:
        """Whether auth/CSRF cookies should carry the Secure attribute.

        COOKIE_SECURE, when set, always wins. Otherwise: Secure in production
        unless frontend_url says the site is served over plain HTTP (an
        air-gapped / intranet box without TLS) — Secure cookies never reach
        the server there, which breaks login silently.
        """
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.is_production and not self.frontend_url.lower().startswith(
            "http://"
        )
