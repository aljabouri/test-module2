"""Unit guards for the new modules: fingerprint confidence wording (BR-FP-01),
SSRF guard (VAL-PROP-01), auth primitives, billing matrix, PDF sealing."""
import json

import pytest

from konformos.api.security import (
    TokenClaims,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from konformos.billing.service import (
    InvalidSignature,
    verify_stripe_signature,
)
from konformos.fingerprint.engine import fingerprint_html
from konformos.scan.crawler import UnsafeUrl, assert_public_host


def test_fingerprint_wordpress_theme():
    html = ('<html><head><meta name="generator" content="WordPress 6.5">'
            '<link href="/wp-content/themes/storefront/style.css"></head>'
            '<body class="woocommerce"></body></html>')
    result = fingerprint_html(html)
    assert result.platform == "woocommerce"
    assert result.theme == {"name": "storefront"}
    assert result.platform_version == "6.5"
    assert result.detection_confidence["platform"] >= 0.7
    assert result.raw_signals  # evidence kept for audit


def test_fingerprint_shopware():
    html = ('<html><head><meta name="generator" content="Shopware 6.5.8">'
            '<script src="/bundles/storefront/js/all.js"></script></head></html>')
    result = fingerprint_html(html)
    assert result.platform == "shopware"
    assert result.detection_confidence["platform"] >= 0.9
    assert result.platform_display == "shopware"


def test_fingerprint_unknown_claims_nothing():
    result = fingerprint_html("<html><body>plain site</body></html>")
    assert result.platform == "unknown"
    assert result.platform_display == "unknown"  # BR-FP-01: no guessing
    assert result.detection_confidence["platform"] == 0.0


def test_ssrf_guard_rejects_private(monkeypatch):
    monkeypatch.delenv("KONFORMOS_ALLOW_PRIVATE_URLS", raising=False)
    for url in ("http://127.0.0.1/", "http://localhost/", "ftp://example.com/"):
        with pytest.raises(UnsafeUrl):
            assert_public_host(url)


def test_ssrf_guard_override_for_dev(monkeypatch):
    monkeypatch.setenv("KONFORMOS_ALLOW_PRIVATE_URLS", "1")
    assert_public_host("http://127.0.0.1:8000/")  # no raise


def test_password_hash_roundtrip_and_min_length():
    hashed = hash_password("a-long-password-123")
    assert verify_password(hashed, "a-long-password-123")
    assert not verify_password(hashed, "wrong-password-123")
    with pytest.raises(ValueError, match="VAL-USER-01"):
        hash_password("short")


def test_jwt_roundtrip():
    import uuid
    claims = TokenClaims(uuid.uuid4(), uuid.uuid4(), "owner", False)
    decoded = decode_token(create_token(claims))
    assert decoded.user_id == claims.user_id
    assert decoded.role == "owner"


def test_stripe_signature_scheme():
    import hashlib
    import hmac as hmac_module
    import time

    secret, payload = "whsec_test", b'{"id":"evt_1"}'
    timestamp = str(int(time.time()))
    signature = hmac_module.new(
        secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256
    ).hexdigest()
    verify_stripe_signature(payload, f"t={timestamp},v1={signature}", secret)
    with pytest.raises(InvalidSignature):
        verify_stripe_signature(payload, f"t={timestamp},v1=deadbeef", secret)


def test_pdf_dossier_sealing(tmp_path, monkeypatch):
    monkeypatch.setenv("KONFORMOS_STORAGE_DIR", str(tmp_path))
    from konformos.dossier.pdf import generate_pdf_dossier, verify_pdf_dossier

    result = generate_pdf_dossier(
        jurisdictions=["DE"], pack_versions={"DE": "DE-2026.1"},
        readiness={"DE": 72}, gaps=[{"rule_code": "wcag-2.2-1.4.3",
                                     "pack_version": "DE-2026.1", "penalty": 6.4,
                                     "pages_affected": 2}],
        generated_at="2026-07-04T12:00:00+00:00",
        timeline_length=4, timeline_head_hash="ab" * 32,
        engine_versions={"internal": "internal-0.1"},
        pages_scanned=5, rules_evaluated=23, rules_manual_pending=32,
        scoring_version="1.0",
    )
    assert result.pdf_path.is_file()
    assert verify_pdf_dossier(result.pdf_path, result.dossier_hash)  # INV-DS-01
    raw = result.pdf_path.read_bytes()

    # decompress content streams to inspect the rendered text
    import re
    import zlib
    text = b""
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.DOTALL):
        try:
            text += zlib.decompress(match.group(1))
        except zlib.error:
            text += match.group(1)
    assert b"DE-2026.1" in text  # INV-DS-02: pack version inside the document
    lowered = text.lower()
    for forbidden in (b"certified", b"guaranteed", b"zertifiziert"):  # INV-DS-03
        assert forbidden not in lowered
    # tampering breaks the seal
    result.pdf_path.write_bytes(raw + b" ")
    assert not verify_pdf_dossier(result.pdf_path, result.dossier_hash)


def test_rate_limit_middleware(monkeypatch):
    # NFR-RATE-01: token bucket returns 429 + Retry-After past the limit
    monkeypatch.setenv("KONFORMOS_RATE_LIMIT_PER_MIN", "3")
    from fastapi.testclient import TestClient

    from konformos.api.main import create_app
    from konformos.registry.loader import load_catalog

    client = TestClient(create_app(load_catalog()))
    for _ in range(3):
        assert client.get("/v1/catalog/rule-packs").status_code == 200
    blocked = client.get("/v1/catalog/rule-packs")
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"] == "60"
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert client.get("/health").status_code == 200  # health is exempt
