"""System diagnostics — model connectivity testing and install readiness.

Two jobs:

* ``diagnose_model`` runs a real round-trip against a configured LLM and
  reports *each step* (config found → protocol → endpoint → key → live call)
  plus, on failure, a classified error with a plain-English "why" and a
  suggested fix. On success it explains why the hook-up is healthy (protocol,
  endpoint, latency, tokens, and the actual reply). This is what powers the
  admin "Test" button — admins should never be left guessing whether a model
  is wired up correctly.

* ``build_readiness`` aggregates the few settings a fresh install genuinely
  needs (a working LLM is a hard blocker; OCR and auth are graded softer) into
  a checklist the admin UI renders as a setup surface.
"""

from __future__ import annotations

import time
from typing import Any

from app.models.system_config import SystemConfig
from app.services.llm_service import (
    _get_model_endpoint_sync,
    detect_api_protocol,
    get_agent_model,
)
from app.utils.encryption import decrypt_value

# Protocols that talk to a hosted, credentialed service. For these a missing
# API key is almost always the real cause of an auth failure, so we flag it.
_HOSTED_PROTOCOLS = ("openai", "anthropic", "openrouter")


def _classify_error(exc: Exception) -> dict[str, str]:
    """Map a raw provider exception to a category + human why/fix.

    Providers (OpenAI SDK, Anthropic, httpx) surface wildly different
    exception types and messages, so we sniff the type name and message text
    rather than catching specific classes. The goal is a useful nudge, not
    forensic precision.
    """
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    raw = str(exc)

    def has(*needles: str) -> bool:
        return any(n in msg or n in name for n in needles)

    if has("authentication", "unauthorized", "401", "403", "invalid api key", "invalid_api_key", "api key"):
        return {
            "category": "auth",
            "title": "Authentication rejected",
            "why": "The provider refused the credentials — the API key is missing, wrong, expired, or lacks access to this model.",
            "fix": "Open this model, re-enter the API key, and save. For OpenAI/Anthropic/OpenRouter the key must match the endpoint you pointed at.",
            "raw": raw,
        }
    if has("not found", "does not exist", "no such model", "model_not_found", "unknown model", "404"):
        return {
            "category": "model_not_found",
            "title": "Model not found at endpoint",
            "why": "The endpoint answered but does not serve a model by this exact name. Model IDs are case- and slash-sensitive.",
            "fix": "Check the Model Name matches the provider's ID exactly (e.g. 'gpt-4o', 'anthropic/claude-haiku-4-5'). Use 'Probe' to see what the endpoint serves.",
            "raw": raw,
        }
    if has("timeout", "timed out", "deadline"):
        return {
            "category": "timeout",
            "title": "Request timed out",
            "why": "The endpoint accepted the connection but did not reply in time. Common with a cold local model or an overloaded gateway.",
            "fix": "Retry — first calls to a local model can be slow while it loads. If it persists, the endpoint or model is overloaded or unreachable.",
            "raw": raw,
        }
    if has("rate limit", "429", "too many requests", "quota", "insufficient_quota"):
        return {
            "category": "rate_limit",
            "title": "Rate limited or out of quota",
            "why": "The provider throttled the request or the account is out of credit. The credentials themselves are valid.",
            "fix": "Wait and retry, or check billing/quota on the provider account. The model is otherwise correctly configured.",
            "raw": raw,
        }
    if has("connect", "connection", "getaddrinfo", "refused", "name or service", "ssl", "certificate", "502", "503", "could not resolve"):
        return {
            "category": "connection",
            "title": "Could not reach the endpoint",
            "why": "The request never got a valid response — the endpoint URL is wrong, the host is down, or it is not reachable from the server.",
            "fix": "Verify the Endpoint URL (scheme + host + path, e.g. 'https://host/v1'). For a self-hosted model confirm it is running and reachable from this server.",
            "raw": raw,
        }
    return {
        "category": "unknown",
        "title": "Model call failed",
        "why": "The call failed before a usable reply came back. See the raw error below for the provider's exact words.",
        "fix": "Read the raw error — it usually names the field at fault. Re-check the model name, endpoint, protocol, and key.",
        "raw": raw,
    }


async def diagnose_model(cfg: SystemConfig, index: int) -> dict[str, Any]:
    """Run a real completion against ``available_models[index]`` and explain it.

    Returns a structured diagnostic (never raises for model-side failures):
    a per-step ``checks`` list, resolved protocol/endpoint, latency, tokens,
    the actual reply on success, and a classified ``error`` on failure.
    """
    if index < 0 or index >= len(cfg.available_models):
        return {
            "ok": False,
            "summary": "No such model.",
            "checks": [{"label": "Model configuration", "ok": False, "detail": f"No model at index {index}."}],
            "error": {
                "category": "config",
                "title": "Model not found",
                "why": "This model is no longer in the configured list — it may have been deleted.",
                "fix": "Refresh the page and test an existing model.",
                "raw": "",
            },
        }

    model_cfg = cfg.available_models[index]
    model_name = (model_cfg.get("name") or "").strip()
    tag = model_cfg.get("tag") or ""
    config_doc = cfg.model_dump()

    checks: list[dict[str, Any]] = []

    # Step 1 — configuration present
    checks.append({
        "label": "Model configuration",
        "ok": bool(model_name),
        "detail": f"Found '{model_name}' (tag: {tag})." if model_name else "Model has no name set.",
    })

    # Step 2 — protocol resolution
    protocol = detect_api_protocol(model_name, model_cfg)
    explicit = bool((model_cfg.get("api_protocol") or "").strip())
    checks.append({
        "label": "API protocol",
        "ok": True,
        "detail": f"{protocol}" + ("" if explicit else " (auto-detected from the model name)"),
    })

    # Step 3 — endpoint resolution
    endpoint = _get_model_endpoint_sync(model_name, config_doc)
    endpoint_label = endpoint or "provider default"
    # Hosted providers ship a default base URL, so a blank endpoint is fine
    # for them; self-hosted protocols need one.
    endpoint_ok = bool(endpoint) or protocol in _HOSTED_PROTOCOLS
    checks.append({
        "label": "Endpoint",
        "ok": endpoint_ok,
        "detail": (
            endpoint if endpoint
            else (f"Using the built-in {protocol} default URL." if endpoint_ok
                  else f"No endpoint set — {protocol} needs an explicit endpoint URL.")
        ),
    })

    # Step 4 — credential presence
    raw_key = (model_cfg.get("api_key") or "")
    has_key = bool(raw_key and decrypt_value(raw_key))
    key_needed = protocol in _HOSTED_PROTOCOLS
    checks.append({
        "label": "API key",
        "ok": has_key or not key_needed,
        "detail": (
            "Stored and decrypted." if has_key
            else (f"No key set — {protocol} endpoints normally require one." if key_needed
                  else "No key set (fine for a local/unauthenticated endpoint).")
        ),
    })

    # Step 5 — live round-trip (source of truth)
    started = time.perf_counter()
    try:
        from pydantic_ai import Agent

        model = get_agent_model(model_name, system_config_doc=config_doc)
        agent = Agent(model, system_prompt="You are a connectivity probe. Reply with exactly: ok")
        from app.services.metering import metered_async
        async with metered_async("diagnostics"):
            result = await agent.run("Say ok")
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        reply = (result.output or "").strip()
        usage = result.usage()
        tokens = {
            "request": getattr(usage, "request_tokens", None),
            "response": getattr(usage, "response_tokens", None),
            "total": getattr(usage, "total_tokens", None),
        }
        checks.append({
            "label": "Live completion",
            "ok": True,
            "detail": f"Replied in {elapsed_ms} ms: \"{reply[:120]}\"",
        })
        return {
            "ok": True,
            "model": model_name,
            "tag": tag,
            "protocol": protocol,
            "endpoint": endpoint_label,
            "checks": checks,
            "latency_ms": elapsed_ms,
            "tokens": tokens,
            "response_preview": reply[:300],
            "error": None,
            "summary": (
                f"Connected. '{model_name}' answered over {protocol} in {elapsed_ms} ms"
                + (f" ({tokens['total']} tokens)." if tokens.get("total") else ".")
            ),
        }
    except Exception as exc:  # noqa: BLE001 — provider errors are diverse; classify below
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        error = _classify_error(exc)
        checks.append({
            "label": "Live completion",
            "ok": False,
            "detail": error["title"],
        })
        return {
            "ok": False,
            "model": model_name,
            "tag": tag,
            "protocol": protocol,
            "endpoint": endpoint_label,
            "checks": checks,
            "latency_ms": elapsed_ms,
            "tokens": None,
            "response_preview": "",
            "error": error,
            "summary": f"{error['title']} — {model_name} did not respond correctly.",
        }


def build_readiness(cfg: SystemConfig) -> dict[str, Any]:
    """Aggregate the settings a fresh install needs into a graded checklist.

    Severity tiers, because the settings are not equal:
    * ``blocker``     — the app is unusable without it (a working LLM).
    * ``recommended`` — degrades gracefully but admins should set it (OCR, auth).
    * ``optional``    — polish.

    Status is presence-based (no live calls — the per-model "Test" button does
    the expensive round-trip). ``action_target`` is a stable key the frontend
    maps to the right config section.
    """
    models = cfg.available_models or []
    default_model = (cfg.default_model or "").strip()
    auth_methods = list(getattr(cfg, "auth_methods", []) or [])
    oauth_providers = list(getattr(cfg, "oauth_providers", []) or [])

    items: list[dict[str, Any]] = []

    # --- LLM (blocker) ---------------------------------------------------
    if not models:
        llm_status, llm_summary = "missing", "No language model is connected yet."
    elif not default_model:
        llm_status, llm_summary = "incomplete", f"{len(models)} model(s) configured, but no default is set."
    else:
        llm_status, llm_summary = "configured", f"{len(models)} model(s) connected; default is '{default_model}'."
    items.append({
        "key": "llm",
        "title": "Connect a language model",
        "severity": "blocker",
        "status": llm_status,
        "summary": llm_summary,
        "unlocks": "Extraction, chat, and every workflow — the app cannot run AI features without at least one working model.",
        "action_label": "Add a model" if llm_status == "missing" else ("Set a default" if llm_status == "incomplete" else "Manage models"),
        "action_target": "models",
    })

    # --- OCR (recommended) ----------------------------------------------
    ocr_status = "configured" if (cfg.ocr_endpoint or "").strip() else "missing"
    items.append({
        "key": "ocr",
        "title": "Enable OCR for scanned PDFs",
        "severity": "recommended",
        "status": ocr_status,
        "summary": "OCR endpoint configured." if ocr_status == "configured"
                   else "No OCR endpoint — scanned/image PDFs fall back to basic text extraction.",
        "unlocks": "High-quality text from scanned and image-only PDFs. Without it those documents extract poorly but still upload.",
        "action_label": "Configure OCR",
        "action_target": "ocr",
    })

    # --- Auth (recommended) ---------------------------------------------
    auth_configured = bool(auth_methods or oauth_providers)
    items.append({
        "key": "auth",
        "title": "Choose sign-in methods",
        "severity": "recommended",
        "status": "configured" if auth_configured else "missing",
        "summary": (f"{len(auth_methods)} method(s), {len(oauth_providers)} OAuth provider(s)." if auth_configured
                    else "Using defaults — review how users sign in."),
        "unlocks": "Single sign-on and password policy for your users.",
        "action_label": "Configure sign-in",
        "action_target": "auth",
    })

    blockers_remaining = sum(
        1 for it in items if it["severity"] == "blocker" and it["status"] != "configured"
    )
    return {
        "ready": blockers_remaining == 0,
        "blockers_remaining": blockers_remaining,
        "items": items,
    }
