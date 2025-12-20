import json


from app.modules.utils import analytics as utils_analytics
from app.modules.utils import content as utils_content
from app.modules.utils import network as utils_network
from app.modules.utils import links as utils_links
from app.modules.search import cache as search_cache
import app.link_preview as link_preview


def test_update_post_score_with_missing_values(session):
    post = utils_analytics.models.Post(owner_id=1, title="t", content="c", is_safe_content=True)
    session.add(post)
    session.commit()
    utils_analytics.update_post_score(session, post)
    assert post.score >= 0


def test_create_default_categories_no_duplicates(session):
    utils_analytics.create_default_categories(session)
    before = session.query(utils_analytics.models.Category).count()
    utils_analytics.create_default_categories(session)
    after = session.query(utils_analytics.models.Category).count()
    assert before == after


def test_offensive_classifier_stub_in_test(monkeypatch):
    monkeypatch.setattr(utils_content, "USE_LIGHTWEIGHT_NLP", True)
    utils_content._offensive_classifier = None
    classifier = utils_content._get_offensive_classifier()
    res = classifier("hello")
    assert isinstance(res, list)


def test_get_client_ip_header(monkeypatch):
    request = type("Req", (), {"headers": {"X-Forwarded-For": "1.1.1.1,2.2.2.2"}, "client": type("c", (), {"host": "3.3.3.3"})})()
    assert utils_network.get_client_ip(request) == "1.1.1.1"


def test_detect_ip_evasion_handles_programming_error(monkeypatch):
    class BoomSession:
        def query(self, *_, **__):
            raise Exception("db down")
    assert utils_network.is_ip_banned(BoomSession(), "1.1.1.1") is False


def test_links_update_link_preview_no_preview(monkeypatch):
    monkeypatch.setattr(utils_links, "extract_link_preview", lambda url: None)
    class DummyDB:
        def query(self, *_):
            return self
        def filter(self, *_):
            return self
        def update(self, *_):
            self.updated = True
        def commit(self):
            self.committed = True
    db = DummyDB()
    utils_links.update_link_preview(db, message_id=1, url="bad")
    assert not hasattr(db, "updated")


def test_link_preview_unsupported_content_type(monkeypatch):
    class DummyResponse:
        status_code = 200
        headers = {"Content-Type": "application/octet-stream"}
        text = "data"
    monkeypatch.setattr(link_preview.validators, "url", lambda u: True)
    monkeypatch.setattr(link_preview.requests, "get", lambda u, timeout=5: DummyResponse())
    result = link_preview.extract_link_preview("http://example.com/file.bin")
    assert result is None


def test_search_cache_ttl(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.values = {}
        def setex(self, key, ttl, val):
            self.values[key] = json.dumps(val)
        def get(self, key):
            return self.values.get(key)
    fake = FakeRedis()
    monkeypatch.setattr(search_cache, "_client", lambda: fake)
    search_cache.set_cached_json("k", {"x": 1}, ttl_seconds=1)
    val = search_cache.get_cached_json("k")
    if isinstance(val, str):
        val = json.loads(val)
    assert val == {"x": 1}
