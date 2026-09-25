"""POST /config/auth/saml/parse-metadata — what the admin form is auto-filled with.

python3-saml flattens an IdP's certificates to a single ``x509cert`` only
when one cert serves both signing and encryption. Shibboleth publishes
distinct certs, which come back as ``x509certMulti`` and used to be reported
as a missing signing certificate. These tests feed real metadata XML through
the real parser so the shape being handled is the parser's, not a guess.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.routers.admin import SamlMetadataRequest, parse_saml_metadata

SIGNING_CERT = "MIIBsigning0000000000000000000000000000000000000000000000000000"
ENCRYPTION_CERT = "MIIBencryption00000000000000000000000000000000000000000000000000"
ROLLOVER_CERT = "MIIBrollover000000000000000000000000000000000000000000000000000"


def _key(use: str | None, cert: str) -> str:
    use_attr = f' use="{use}"' if use else ""
    return (
        f"<md:KeyDescriptor{use_attr}>"
        '<ds:KeyInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">'
        f"<ds:X509Data><ds:X509Certificate>{cert}</ds:X509Certificate></ds:X509Data>"
        "</ds:KeyInfo></md:KeyDescriptor>"
    )


def _metadata(keys: str, sso: bool = True) -> str:
    sso_xml = (
        '<md:SingleSignOnService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect" '
        'Location="https://idp.example.edu/idp/profile/SAML2/Redirect/SSO"/>'
        if sso
        else ""
    )
    return (
        '<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" '
        'entityID="https://idp.example.edu/idp/shibboleth">'
        '<md:IDPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">'
        f"{keys}{sso_xml}"
        "</md:IDPSSODescriptor></md:EntityDescriptor>"
    )


async def _parse(xml: str) -> dict:
    with patch("app.routers.admin._require_superadmin", new_callable=AsyncMock):
        return await parse_saml_metadata(SamlMetadataRequest(metadata_xml=xml), user=None)


@pytest.mark.asyncio
async def test_single_shared_cert_still_parses():
    result = await _parse(_metadata(_key(None, SIGNING_CERT)))

    assert result["idp_entity_id"] == "https://idp.example.edu/idp/shibboleth"
    assert result["idp_sso_url"] == "https://idp.example.edu/idp/profile/SAML2/Redirect/SSO"
    assert result["idp_x509_cert"] == SIGNING_CERT
    assert "idp_x509_cert_alternates" not in result


@pytest.mark.asyncio
async def test_distinct_signing_and_encryption_certs_use_the_signing_one():
    """The Shibboleth layout: parser emits x509certMulti, not x509cert."""
    result = await _parse(
        _metadata(_key("signing", SIGNING_CERT) + _key("encryption", ENCRYPTION_CERT))
    )

    assert result["idp_x509_cert"] == SIGNING_CERT
    assert "idp_x509_cert_alternates" not in result


@pytest.mark.asyncio
async def test_key_rollover_surfaces_alternate_signing_certs():
    result = await _parse(
        _metadata(
            _key("signing", SIGNING_CERT)
            + _key("signing", ROLLOVER_CERT)
            + _key("encryption", ENCRYPTION_CERT)
        )
    )

    assert result["idp_x509_cert"] == SIGNING_CERT
    assert result["idp_x509_cert_alternates"] == [ROLLOVER_CERT]


@pytest.mark.asyncio
async def test_422_names_only_the_fields_actually_missing():
    with pytest.raises(HTTPException) as exc:
        await _parse(_metadata(_key("signing", SIGNING_CERT), sso=False))

    assert exc.value.status_code == 422
    assert exc.value.detail == "Metadata is missing: HTTP-Redirect SSO URL."


@pytest.mark.asyncio
async def test_encryption_only_metadata_reports_missing_signing_cert():
    with pytest.raises(HTTPException) as exc:
        await _parse(_metadata(_key("encryption", ENCRYPTION_CERT) + _key("encryption", ROLLOVER_CERT)))

    assert exc.value.status_code == 422
    assert "signing certificate" in exc.value.detail
