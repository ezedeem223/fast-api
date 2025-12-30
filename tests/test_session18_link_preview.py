from types import SimpleNamespace

from app import link_preview


class DummyResp:
    def __init__(self, html: str, status: int = 200):
        self.content = html.encode()
        self.status_code = status


def test_invalid_url_returns_none(monkeypatch):
    assert link_preview.extract_link_preview("not-a-url") is None


def test_extract_link_preview_with_og(monkeypatch):
    html = """
    <html>
      <head>
        <title>My Site</title>
        <meta property="og:description" content="og desc">
        <meta property="og:image" content="http://img/one.png">
      </head>
    </html>
    """
    captured = {}

    def fake_get(url, timeout):
        captured["url"] = url
        captured["timeout"] = timeout
        return DummyResp(html)

    monkeypatch.setattr(link_preview.requests, "get", fake_get)
    monkeypatch.setattr(link_preview, "validators", SimpleNamespace(url=lambda u: True))

    preview = link_preview.extract_link_preview("http://example.com")
    assert preview["title"] == "My Site"
    assert preview["description"] == "og desc"
    assert preview["image"] == "http://img/one.png"
    assert captured["timeout"] == 5


def test_extract_link_preview_fallback_title(monkeypatch):
    html = """
    <html><head><title>Fallback Title</title></head><body></body></html>
    """

    monkeypatch.setattr(
        link_preview.requests, "get", lambda url, timeout: DummyResp(html)
    )
    monkeypatch.setattr(link_preview, "validators", SimpleNamespace(url=lambda u: True))

    preview = link_preview.extract_link_preview("http://fallback.com")
    assert preview["title"] == "Fallback Title"
    assert preview["description"] == ""
    assert preview["image"] == ""


def test_extract_link_preview_handles_errors(monkeypatch):
    def raise_get(*a, **k):
        raise RuntimeError("fail")

    monkeypatch.setattr(link_preview.requests, "get", raise_get)
    monkeypatch.setattr(link_preview, "validators", SimpleNamespace(url=lambda u: True))

    assert link_preview.extract_link_preview("http://err.com") is None


def test_extract_link_preview_non_200_returns_none(monkeypatch):
    html = "<html><head><title>Denied</title></head></html>"

    monkeypatch.setattr(
        link_preview.requests, "get", lambda url, timeout: DummyResp(html, status=500)
    )
    monkeypatch.setattr(link_preview, "validators", SimpleNamespace(url=lambda u: True))

    assert link_preview.extract_link_preview("http://example.com/fail") is None


def test_blocked_domain_returns_none(monkeypatch):
    monkeypatch.setattr(link_preview, "validators", SimpleNamespace(url=lambda u: True))
    monkeypatch.setattr(
        link_preview.requests, "get", lambda url, timeout: DummyResp("<html></html>")
    )

    # Domain is in BLOCKED_DOMAINS
    assert link_preview.extract_link_preview("http://malware.test/page") is None


def test_banned_content_filters(monkeypatch):
    html = """
    <html>
      <head>
        <title>Phishing attempt</title>
        <meta property="og:description" content="innocent">
      </head>
    </html>
    """
    monkeypatch.setattr(
        link_preview.requests, "get", lambda url, timeout: DummyResp(html)
    )
    monkeypatch.setattr(link_preview, "validators", SimpleNamespace(url=lambda u: True))

    assert link_preview.extract_link_preview("http://safe.test/page") is None
