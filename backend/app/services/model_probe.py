"""Probe LLM endpoints for their serving context window.

Model-card / docs context length often disagrees with what the endpoint
actually accepts (e.g. Llama-3 advertises 131k but a vLLM deployment may
have been started with --max-model-len 65536 to fit GPU memory). This
module asks the *server* directly so SystemConfig stops relying on
substring fallbacks that overshoot.

Returns a dataclass so the admin UI can show both the discovered value
and where it came from (or why nothing could be discovered).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 15.0


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class ProbeResult:
    context_window: Optional[int]
    source: str  # "vllm_max_model_len" | "openrouter_context_length" | "ollama_show" | "openai_no_field" | "anthropic_no_probe" | "no_endpoint" | "error"
    detail: Optional[str] = None  # human-readable explanation, esp. on miss
    raw: Optional[dict] = None  # the matched model entry, for debugging

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Protocol-specific probes
# ---------------------------------------------------------------------------


def _normalize_openai_base(endpoint: str) -> str:
    base = endpoint.rstrip("/")
    if not (base.endswith("/v1") or base.endswith("/api/v1")):
        base = f"{base}/v1"
    return base


def _match_model_entry(entries: list[dict], model_name: str) -> Optional[dict]:
    """Find the model dict whose id matches `model_name` (case-insensitive)."""
    if not model_name:
        # No name given — just take the first entry if there's one
        return entries[0] if entries else None
    target = model_name.lower()
    # Exact id match first
    for m in entries:
        if str(m.get("id", "")).lower() == target:
            return m
    # Some servers prefix the model; try suffix match
    for m in entries:
        mid = str(m.get("id", "")).lower()
        if mid.endswith("/" + target) or mid.endswith(":" + target):
            return m
    return None


async def _probe_openai_compatible(
    *,
    endpoint: str,
    api_key: str,
    model_name: str,
    protocol_label: str,
) -> ProbeResult:
    """Hit `/v1/models` on an OpenAI-compatible endpoint.

    vLLM puts the serving cap in `max_model_len`. OpenRouter exposes
    `context_length`. The official OpenAI API exposes neither (the
    response only carries ids), so this returns `openai_no_field` in
    that case rather than pretending.
    """
    if not endpoint:
        return ProbeResult(None, "no_endpoint", "Endpoint URL is empty.")

    base = _normalize_openai_base(endpoint)
    url = f"{base}/models"
    headers: dict[str, str] = {}
    if api_key and api_key != "no-api-key":
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(url, headers=headers)
    except httpx.ConnectError as e:
        return ProbeResult(None, "error", f"Could not connect to {url}: {e}")
    except httpx.TimeoutException:
        return ProbeResult(None, "error", f"Timed out fetching {url}")
    except Exception as e:  # pragma: no cover  - defensive
        return ProbeResult(None, "error", f"Probe failed: {e}")

    if resp.status_code == 401:
        return ProbeResult(None, "error", "Endpoint rejected the API key (401).")
    if resp.status_code == 404:
        return ProbeResult(None, "error", f"{url} returned 404 — endpoint may not expose /v1/models.")
    if resp.status_code >= 400:
        return ProbeResult(None, "error", f"{url} returned HTTP {resp.status_code}.")

    try:
        payload = resp.json()
    except Exception as e:
        return ProbeResult(None, "error", f"Response from {url} was not JSON: {e}")

    entries: list[dict] = []
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            entries = [m for m in data if isinstance(m, dict)]
    if not entries:
        return ProbeResult(None, "error", f"{url} returned no model entries.")

    match = _match_model_entry(entries, model_name)
    if match is None:
        ids = ", ".join(str(m.get("id", "?")) for m in entries[:5])
        return ProbeResult(
            None,
            "error",
            f"Endpoint listed {len(entries)} model(s) but none matched '{model_name}'. Seen: {ids}",
        )

    # Field priority: vLLM's max_model_len is authoritative; OpenRouter
    # ships context_length; some servers use context_window directly.
    for field, label in (
        ("max_model_len", "vllm_max_model_len"),
        ("context_length", "openrouter_context_length"),
        ("context_window", f"{protocol_label}_context_window"),
    ):
        raw_val = match.get(field)
        try:
            val = int(raw_val) if raw_val is not None else 0
        except (TypeError, ValueError):
            val = 0
        if val > 0:
            return ProbeResult(val, label, None, raw=match)

    # Models endpoint exists, model matched, but no context field present.
    # That's the canonical OpenAI shape.
    return ProbeResult(
        None,
        "openai_no_field",
        "Endpoint listed the model but did not report a context length (typical for the official OpenAI API).",
        raw=match,
    )


async def _probe_ollama(*, endpoint: str, model_name: str) -> ProbeResult:
    """Hit `POST /api/show` on Ollama and read context_length from model_info."""
    if not endpoint:
        return ProbeResult(None, "no_endpoint", "Endpoint URL is empty.")
    if not model_name:
        return ProbeResult(None, "error", "Model name is required to probe Ollama.")

    base = endpoint.rstrip("/")
    url = f"{base}/api/show"
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.post(url, json={"name": model_name})
    except httpx.ConnectError as e:
        return ProbeResult(None, "error", f"Could not connect to {url}: {e}")
    except httpx.TimeoutException:
        return ProbeResult(None, "error", f"Timed out fetching {url}")
    except Exception as e:  # pragma: no cover
        return ProbeResult(None, "error", f"Probe failed: {e}")

    if resp.status_code == 404:
        return ProbeResult(None, "error", f"Ollama has no model named '{model_name}'.")
    if resp.status_code >= 400:
        return ProbeResult(None, "error", f"{url} returned HTTP {resp.status_code}.")

    try:
        payload = resp.json()
    except Exception as e:
        return ProbeResult(None, "error", f"Response from {url} was not JSON: {e}")

    info = payload.get("model_info") if isinstance(payload, dict) else None
    if isinstance(info, dict):
        # Ollama keys context length under "<arch>.context_length", e.g.
        # "llama.context_length" or "qwen2.context_length". Walk for the
        # first *.context_length key.
        for key, value in info.items():
            if isinstance(key, str) and key.endswith(".context_length"):
                try:
                    val = int(value)
                except (TypeError, ValueError):
                    continue
                if val > 0:
                    return ProbeResult(val, "ollama_show", None, raw={key: val})

    # Older Ollama versions expose `parameters` as a flat string blob
    # with "num_ctx" lines.
    params = payload.get("parameters") if isinstance(payload, dict) else None
    if isinstance(params, str):
        for line in params.splitlines():
            parts = line.strip().split()
            if len(parts) == 2 and parts[0] == "num_ctx":
                try:
                    val = int(parts[1])
                except ValueError:
                    continue
                if val > 0:
                    return ProbeResult(val, "ollama_show", None, raw={"num_ctx": val})

    return ProbeResult(
        None,
        "error",
        "Ollama did not report a context length for this model.",
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def probe_context_window(
    *,
    endpoint: str,
    api_protocol: str,
    api_key: str,
    model_name: str,
) -> ProbeResult:
    """Ask the configured endpoint what context window it serves.

    Routes by `api_protocol`. `api_key` is the *decrypted* key — callers
    are responsible for decrypting before calling. The result is safe to
    return to clients; it contains no credentials.
    """
    protocol = (api_protocol or "").strip().lower()

    if protocol == "anthropic":
        # Anthropic's /v1/models response has historically omitted
        # context length, and treating any of its values as authoritative
        # has bitten us before. Don't pretend.
        return ProbeResult(
            None,
            "anthropic_no_probe",
            "Anthropic's API doesn't expose context length — set context_window manually from the model card.",
        )

    if protocol == "ollama":
        return await _probe_ollama(endpoint=endpoint, model_name=model_name)

    # vllm / openai / openrouter / "" (auto / insightai) all speak the
    # OpenAI-compatible `/v1/models` shape. Probe it; the field-priority
    # code inside handles whichever flavor of context length is present.
    return await _probe_openai_compatible(
        endpoint=endpoint,
        api_key=api_key,
        model_name=model_name,
        protocol_label=protocol or "openai",
    )
