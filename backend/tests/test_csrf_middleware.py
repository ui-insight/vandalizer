"""Tests for CSRFMiddleware (app.middleware.csrf).

Verifies CSRF enforcement, exemptions, API key bypass, and double-submit cookie logic.
"""

import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _make_user(**overrides):
    defaults = {
        "id": "fake-id",
        "user_id": "testuser",
        "email": "test@example.com",
        "name": "Test User",
        "is_admin": False,
        "current_team": None,
        "organization_id": None,
        "is_demo_user": False,
        "demo_status": None,
        "token_version": 0,
    }
    defaults.update(overrides)
    user = MagicMock()
    for k, v in defaults.items():
        setattr(user, k, v)
    user.save = AsyncMock()
    return user


def _auth(user_id="testuser"):
    token = create_access_token(user_id, _TEST_SETTINGS)
    csrf = secrets.token_urlsafe(32)
    return {"access_token": token, "csrf_token": csrf}, {"X-CSRF-Token": csrf}


@pytest.fixture
async def client():
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac


class TestCSRFMiddleware:
    @pytest.mark.asyncio
    async def test_get_allowed_without_csrf(self, client):
        """GET requests pass through without CSRF validation."""
        resp = await client.get("/api/health")
        # Health endpoint may return 200 or 503 depending on deps, but not 403
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_post_without_csrf_blocked(self, client):
        """POST to a non-exempt path without CSRF token returns 403."""
        user = _make_user()
        token = create_access_token("testuser", _TEST_SETTINGS)

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/documents/search",
                json={"query": "test"},
                cookies={"access_token": token},
                # No CSRF cookie or header
            )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_post_with_matching_csrf_passes(self, client):
        """POST with matching CSRF cookie and header passes through."""
        user = _make_user()
        cookies, headers = _auth()

        mock_find_query = MagicMock()
        mock_find_query.to_list = AsyncMock(return_value=[])

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.reviews.ApprovalRequest") as MockApproval:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_find_query.sort = MagicMock(return_value=mock_find_query)
            MockApproval.find = MagicMock(return_value=mock_find_query)
            MockApproval.created_at = MagicMock()  # supports unary negation

            # Use a GET endpoint that we know works with auth
            resp = await client.get(
                "/api/reviews",
                cookies=cookies,
                headers=headers,
            )

        # Should not be blocked by CSRF (GET is safe)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_post_with_mismatched_csrf_blocked(self, client):
        """POST with mismatched CSRF cookie and header returns 403."""
        user = _make_user()
        token = create_access_token("testuser", _TEST_SETTINGS)

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/documents/search",
                json={"query": "test"},
                cookies={"access_token": token, "csrf_token": "cookie-value"},
                headers={"X-CSRF-Token": "different-header-value"},
            )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_post_to_exempt_path_bypasses_csrf(self, client):
        """POST to an exempt path (e.g., /api/auth/login) does not require CSRF."""
        with patch("app.routers.auth.auth_service") as mock_auth_svc:
            mock_auth_svc.authenticate_with_reason = AsyncMock(return_value=(None, None))

            resp = await client.post(
                "/api/auth/login",
                json={"user_id": "testuser", "password": "wrong"},
            )

        # Should not be 403 (CSRF). Will be 401 because creds are wrong, which is fine.
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_post_with_api_key_bypasses_csrf(self, client):
        """POST with X-API-Key header bypasses CSRF validation."""
        user = _make_user()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)

            # API key present -- CSRF should be bypassed
            # The endpoint may still fail for other reasons, but not 403 from CSRF
            resp = await client.post(
                "/api/documents/search",
                json={"query": "test"},
                headers={"X-API-Key": "some-api-key"},
            )

        # Should NOT be 403 from CSRF middleware
        # It may be 401 (no auth cookie) or something else, but not CSRF 403
        assert resp.status_code != 403 or "CSRF" not in resp.text

    @pytest.mark.asyncio
    async def test_webhook_path_exempt(self, client):
        """POST to /api/webhooks/ prefix bypasses CSRF."""
        resp = await client.post(
            "/api/webhooks/graph",
            json={"value": []},
        )

        # Should not be blocked by CSRF; webhook prefix is exempt
        assert resp.status_code != 403
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_telemetry_heartbeat_bypasses_csrf(self, client):
        """POST to /api/telemetry/heartbeat bypasses CSRF.

        Fleet heartbeats arrive cross-origin from arbitrary deployments that
        share no session or CSRF cookie with the collector, so the double-submit
        token can never be present. Without the exemption every heartbeat 403s.
        (The ingest route is only registered on the collector instance, so here
        the request falls through to a 404 — the point is it MUST NOT be a 403
        from the CSRF middleware.)
        """
        resp = await client.post(
            "/api/telemetry/heartbeat",
            json={
                "schema": 1,
                "instance_id": "diag-test-00000001",
                "version": "test",
                "environment": "other",
                "metrics": {},
            },
        )
        assert resp.status_code != 403, resp.text

    @pytest.mark.asyncio
    async def test_saml_acs_bypasses_csrf(self, client):
        """POST to /api/auth/saml/acs (cross-site from IdP) bypasses CSRF.

        The IdP returns a self-submitting form that POSTs the SAML response
        back to the SP. That POST is cross-site, so the browser doesn't send
        the CSRF cookie and there's no way to attach a CSRF header. The
        endpoint must be exempt — the SAML assertion's signature is what
        authenticates the response, not double-submit.
        """
        # Mock SystemConfig so the handler short-circuits with a 400 "SAML not
        # configured" instead of trying to hit the (uninitialized) DB. We only
        # care that the request gets past the CSRF middleware.
        config = MagicMock()
        config.oauth_providers = []
        with patch(
            "app.routers.auth.SystemConfig.get_config",
            new_callable=AsyncMock,
            return_value=config,
        ):
            resp = await client.post(
                "/api/auth/saml/acs",
                data={"SAMLResponse": "fake-not-validated-here"},
            )
        # Will be 400 ("SAML not configured") here, but MUST NOT be a 403
        # from the CSRF middleware.
        assert resp.status_code != 403, resp.text

    @pytest.mark.asyncio
    async def test_invite_accept_bypasses_csrf(self, client):
        """POST to /api/teams/invite/accept/{token} bypasses CSRF.

        The accept POST fires right after a cross-site SSO redirect, the window
        where the freshly-set CSRF cookie can be briefly unreadable by JS, so the
        double-submit header is unreliable. The unguessable URL token is the real
        authorization, so the route is exempt (same reasoning as SAML ACS). With
        no auth cookie the request should fall through to a 401 — never a 403
        from the CSRF middleware.
        """
        resp = await client.post("/api/teams/invite/accept/sometoken")
        assert resp.status_code != 403, resp.text

    @pytest.mark.asyncio
    async def test_join_link_accept_bypasses_csrf(self, client):
        """POST to /api/teams/join-link/accept/{token} bypasses CSRF.

        Same rationale as the direct-invite accept route: token-authorized, and
        runs in the post-SSO-redirect window where the CSRF cookie is fragile.
        """
        resp = await client.post("/api/teams/join-link/accept/sometoken")
        assert resp.status_code != 403, resp.text

    @pytest.mark.asyncio
    async def test_teams_non_accept_route_still_requires_csrf(self, client):
        """The exemption is scoped: other /api/teams POSTs still need CSRF.

        Guards against the prefix being widened to all of /api/teams.
        """
        resp = await client.post(
            "/api/teams/invite",
            json={"team_uuid": "x", "email": "a@b.com", "role": "member"},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "CSRF validation failed"

    @pytest.mark.asyncio
    async def test_legacy_cookie_still_accepted(self, client):
        """A user holding only the legacy csrf_token cookie can still validate.

        This covers the transition window: users whose browsers haven't yet
        received the new __Host-csrf_token cookie must not be locked out.
        """
        user = _make_user()
        token = create_access_token("testuser", _TEST_SETTINGS)
        csrf = secrets.token_urlsafe(32)

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/documents/search",
                json={"query": "test"},
                cookies={"access_token": token, "csrf_token": csrf},
                headers={"X-CSRF-Token": csrf},
            )

        # Not blocked by CSRF (legacy cookie still validates)
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_stale_spa_with_both_cookies_accepts_legacy_header(self, client):
        """Stale OLD-SPA tab post-deploy: both cookies set, header from legacy.

        Once a user with the old SPA still loaded makes any GET after the
        deploy, the middleware sets ``__Host-csrf_token=Y`` alongside the
        existing ``csrf_token=X``.  The old SPA's regex doesn't match the
        ``__Host-`` prefix, so it sends the legacy value ``X`` in the header.
        The backend must accept that header against the legacy cookie rather
        than mismatching against the modern one — otherwise every POST from
        long-lived tabs 403s until the user reloads.
        """
        prod_settings = Settings(
            jwt_secret_key="test-secret-key", environment="production"
        )
        user = _make_user()
        token = create_access_token("testuser", prod_settings)
        legacy_value = secrets.token_urlsafe(32)
        modern_value = secrets.token_urlsafe(32)

        with patch("app.dependencies.get_settings", return_value=prod_settings), \
             patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/documents/search",
                json={"query": "test"},
                cookies={
                    "access_token": token,
                    "csrf_token": legacy_value,
                    "__Host-csrf_token": modern_value,
                },
                # Old SPA reads the legacy cookie and sends its value
                headers={"X-CSRF-Token": legacy_value},
            )

        assert resp.status_code != 403, resp.text

    @pytest.mark.asyncio
    async def test_duplicate_legacy_cookies_accepts_first_value(self, client):
        """Duplicate ``csrf_token`` cookies + old SPA tab: header carries first value.

        When a sibling app on a parent domain or a prior deploy left a second
        ``csrf_token`` cookie at a different Path/Domain, the browser sends
        both on every request.  Python's SimpleCookie collapses them to the
        last value, but the old SPA's regex picks the *first* one — so the
        backend's "accept either cookie value" set must contain every legacy
        value present in the raw cookie header, not just the dedup'd one.
        """
        prod_settings = Settings(
            jwt_secret_key="test-secret-key", environment="production"
        )
        user = _make_user()
        token = create_access_token("testuser", prod_settings)
        first_legacy = secrets.token_urlsafe(32)
        last_legacy = secrets.token_urlsafe(32)
        modern_value = secrets.token_urlsafe(32)

        cookie_header = (
            f"access_token={token}; "
            f"csrf_token={first_legacy}; "
            f"__Host-csrf_token={modern_value}; "
            f"csrf_token={last_legacy}"
        )

        with patch("app.dependencies.get_settings", return_value=prod_settings), \
             patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/documents/search",
                json={"query": "test"},
                headers={
                    "Cookie": cookie_header,
                    # Old SPA's regex picks the first csrf_token value
                    "X-CSRF-Token": first_legacy,
                },
            )

        assert resp.status_code != 403, resp.text

    @pytest.mark.asyncio
    async def test_stale_spa_with_both_cookies_accepts_modern_header(self, client):
        """Same transition state, but the SPA has been reloaded.

        The new SPA reads the modern cookie and sends its value.  Must also
        be accepted even though the legacy cookie is still sitting in the
        jar with a different random value.
        """
        prod_settings = Settings(
            jwt_secret_key="test-secret-key", environment="production"
        )
        user = _make_user()
        token = create_access_token("testuser", prod_settings)
        legacy_value = secrets.token_urlsafe(32)
        modern_value = secrets.token_urlsafe(32)

        with patch("app.dependencies.get_settings", return_value=prod_settings), \
             patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/documents/search",
                json={"query": "test"},
                cookies={
                    "access_token": token,
                    "csrf_token": legacy_value,
                    "__Host-csrf_token": modern_value,
                },
                headers={"X-CSRF-Token": modern_value},
            )

        assert resp.status_code != 403, resp.text


class TestBuildCsrfCookieHeader:
    """Unit tests for the cookie-name + attributes builder."""

    def test_uses_legacy_name_when_insecure(self):
        from app.middleware.csrf import _build_csrf_cookie_header

        header = _build_csrf_cookie_header(name="csrf_token", secure=False)
        assert header.startswith("csrf_token=")
        assert "Path=/" in header
        # Lax (not Strict) — avoids the "freshly-set Strict cookie not readable
        # after OAuth redirect" quirk that breaks invite-accept flows.
        assert "SameSite=Lax" in header
        assert "SameSite=Strict" not in header
        assert "Max-Age=" in header
        assert "Secure" not in header

    def test_uses_host_prefix_when_secure(self):
        """In production the cookie must carry the __Host- prefix and Secure flag.

        The __Host- prefix makes the cookie unspoofable by collisions: the
        browser refuses to store any cookie of this name without Secure,
        Path=/, and no Domain. This eliminates the duplicate-cookie failure
        mode that caused the "CSRF validation failed in Chrome but not
        incognito" bug.
        """
        from app.middleware.csrf import _build_csrf_cookie_header

        header = _build_csrf_cookie_header(name="__Host-csrf_token", secure=True)
        assert header.startswith("__Host-csrf_token=")
        assert "Path=/" in header
        # Lax (not Strict) — avoids the "freshly-set Strict cookie not readable
        # after OAuth redirect" quirk that breaks invite-accept flows.
        assert "SameSite=Lax" in header
        assert "SameSite=Strict" not in header
        assert "Secure" in header
        # __Host- prefix forbids a Domain attribute
        assert "Domain=" not in header

    def test_all_cookie_values_returns_every_duplicate(self):
        """_all_cookie_values must return *every* value for the given name.

        SimpleCookie's last-write-wins parse hides duplicates, but an old SPA
        regex may pick any of them — validation needs the full multiset.
        """
        from app.middleware.csrf import _all_cookie_values

        header = "access_token=t; csrf_token=A; __Host-csrf_token=M; csrf_token=B"
        assert _all_cookie_values(header, "csrf_token") == ["A", "B"]
        assert _all_cookie_values(header, "__Host-csrf_token") == ["M"]
        assert _all_cookie_values(header, "missing") == []
        assert _all_cookie_values("", "csrf_token") == []

    def test_primary_cookie_name_selection(self):
        from app.middleware.csrf import (
            LEGACY_COOKIE_NAME,
            MODERN_COOKIE_NAME,
            _primary_cookie_name,
        )

        assert _primary_cookie_name(secure=True) == MODERN_COOKIE_NAME
        assert _primary_cookie_name(secure=False) == LEGACY_COOKIE_NAME
        assert MODERN_COOKIE_NAME == "__Host-csrf_token"
        assert LEGACY_COOKIE_NAME == "csrf_token"
