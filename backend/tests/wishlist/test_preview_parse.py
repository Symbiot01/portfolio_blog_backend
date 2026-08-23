"""URL preview HTML parsing and SSRF guards."""

from __future__ import annotations

import pytest

from app.wishlist.adapters.preview import (
    _read_enough_html,
    assert_safe_public_url,
    parse_product_html,
)
from app.wishlist.domain.errors import ValidationError


SAMPLE_HTML = """
<html><head>
<title>Ignored Title</title>
<meta property="og:title" content="Sony WH-1000XM5" />
<meta property="og:image" content="/images/sony.jpg" />
<meta property="product:price:amount" content="349.99" />
<meta property="product:price:currency" content="USD" />
<script type="application/ld+json">
{"@type":"Product","name":"LD Name","offers":{"@type":"Offer","price":"299.00","priceCurrency":"USD"}}
</script>
</head><body></body></html>
"""


def test_parse_prefers_og_meta():
    draft = parse_product_html(SAMPLE_HTML, "https://store.example.com/p/1")
    assert draft["title"] == "Sony WH-1000XM5"
    assert draft["image_url"] == "https://store.example.com/images/sony.jpg"
    assert draft["price"] == 349.99
    assert draft["currency"] == "USD"


def test_parse_jsonld_when_og_missing():
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@type":"Product","name":"Bose QC","image":"https://cdn.example/bose.png",
     "offers":{"price":429,"priceCurrency":"EUR"}}
    </script>
    </head></html>
    """
    draft = parse_product_html(html, "https://shop.example/item")
    assert draft["title"] == "Bose QC"
    assert draft["image_url"] == "https://cdn.example/bose.png"
    assert draft["price"] == 429.0
    assert draft["currency"] == "EUR"


def test_parse_works_on_head_only_truncation():
    """Fetcher stops after </head>; huge bodies must not be required."""
    head_only = SAMPLE_HTML.split("</head>")[0] + "</head>"
    draft = parse_product_html(head_only, "https://store.example.com/p/1")
    assert draft["title"] == "Sony WH-1000XM5"
    assert draft["price"] == 349.99


def test_read_enough_stops_after_head_plus_slack():
    head = b"<html><head><title>x</title></head>"
    assert _read_enough_html(bytearray(head)) is False  # need slack unless cap
    padded = bytearray(head + (b"y" * 70_000))
    assert _read_enough_html(padded) is True


def test_read_enough_stops_at_hard_cap():
    buf = bytearray(b"a" * 520_000)
    assert _read_enough_html(buf) is True


def test_assert_safe_url_rejects_non_http():
    with pytest.raises(ValidationError):
        assert_safe_public_url("ftp://example.com/x")


def test_assert_safe_url_rejects_localhost():
    with pytest.raises(ValidationError):
        assert_safe_public_url("http://localhost/admin")


def test_assert_safe_url_rejects_private_ip_literal():
    with pytest.raises(ValidationError):
        assert_safe_public_url("http://127.0.0.1/secret")
    with pytest.raises(ValidationError):
        assert_safe_public_url("http://192.168.1.10/x")
    with pytest.raises(ValidationError):
        assert_safe_public_url("http://169.254.169.254/latest/meta-data")
