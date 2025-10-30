from app import link_preview


class DummyResponse:
    def __init__(self, html):
        self.content = html.encode("utf-8")


def test_extract_link_preview_invalid_url_returns_none():
    assert link_preview.extract_link_preview("not-a-url") is None


def test_extract_link_preview_parses_meta(monkeypatch):
    html = """
    <html>
      <head>
        <title>Example</title>
        <meta name=\"description\" content=\"Site description\" />
        <meta property=\"og:image\" content=\"https://example.com/image.png\" />
      </head>
    </html>
    """

    monkeypatch.setattr(
        link_preview.requests,
        "get",
        lambda url, timeout=5: DummyResponse(html),
    )

    data = link_preview.extract_link_preview("https://example.com")

    assert data == {
        "title": "Example",
        "description": "Site description",
        "image": "https://example.com/image.png",
        "url": "https://example.com",
    }
