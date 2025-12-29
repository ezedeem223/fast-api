from app import firebase_config


class DummyCred:
    def __init__(self):
        self.calls = 0

    def __call__(self, data):
        self.calls += 1
        return data


class DummyMessaging:
    def __init__(self):
        self.sent = []
        self.topic_subs = []
        self.topic_unsubs = []

    class Notification:
        def __init__(self, title=None, body=None):
            self.title = title
            self.body = body

    class MulticastMessage:
        def __init__(self, tokens, notification=None, data=None):
            self.tokens = tokens
            self.notification = notification
            self.data = data

    class Message:
        def __init__(self, topic=None, notification=None, data=None, token=None):
            self.topic = topic
            self.notification = notification
            self.data = data
            self.token = token

    def send_multicast(self, message):
        self.sent.append(("multicast", message.tokens, message.data))
        return {"success": len(message.tokens)}

    def send(self, message):
        self.sent.append(("single", message.topic or message.token, message.data))
        return "msg-id"

    def subscribe_to_topic(self, tokens, topic):
        self.topic_subs.append((tuple(tokens), topic))
        return {"success": len(tokens)}

    def unsubscribe_from_topic(self, tokens, topic):
        self.topic_unsubs.append((tuple(tokens), topic))
        return {"success": len(tokens)}


def test_initialize_firebase_missing_key(monkeypatch):
    monkeypatch.setattr(firebase_config.settings, "firebase_project_id", "proj")
    monkeypatch.setattr(firebase_config.settings, "firebase_api_key", None, raising=False)
    monkeypatch.setattr(firebase_config.settings, "firebase_auth_domain", "")
    monkeypatch.setattr(firebase_config.settings, "firebase_storage_bucket", "")
    monkeypatch.setattr(firebase_config.settings, "firebase_messaging_sender_id", "")
    monkeypatch.setattr(firebase_config.settings, "firebase_app_id", "")
    monkeypatch.setattr(firebase_config.settings, "firebase_measurement_id", "")
    called = {"init": 0}
    monkeypatch.setattr(firebase_config, "initialize_app", lambda *a, **k: called.__setitem__("init", called["init"] + 1))
    ok = firebase_config.initialize_firebase()
    assert ok is False
    assert called["init"] == 0


def test_initialize_firebase_success(monkeypatch):
    dummy_credentials = DummyCred()
    monkeypatch.setattr(firebase_config, "credentials", type("C", (), {"Certificate": dummy_credentials}))
    monkeypatch.setattr(firebase_config.settings, "firebase_project_id", "proj")
    monkeypatch.setattr(firebase_config.settings, "firebase_api_key", "key")
    monkeypatch.setattr(firebase_config.settings, "firebase_auth_domain", "auth")
    monkeypatch.setattr(firebase_config.settings, "firebase_storage_bucket", "bucket")
    monkeypatch.setattr(firebase_config.settings, "firebase_messaging_sender_id", "sender")
    monkeypatch.setattr(firebase_config.settings, "firebase_app_id", "appid")
    monkeypatch.setattr(firebase_config.settings, "firebase_measurement_id", "mid")

    init_calls = {"count": 0}
    monkeypatch.setattr(firebase_config, "initialize_app", lambda cred, config: init_calls.__setitem__("count", init_calls["count"] + 1))
    ok = firebase_config.initialize_firebase()
    assert ok is True
    assert init_calls["count"] == 1
    assert dummy_credentials.calls == 1


def test_messaging_send_paths(monkeypatch):
    dummy = DummyMessaging()
    monkeypatch.setattr(firebase_config, "messaging", dummy)
    monkeypatch.setattr(firebase_config, "logger", type("L", (), {"error": lambda *a, **k: None, "info": lambda *a, **k: None})())

    resp_multi = firebase_config.send_multicast_notification(["t1", "t2"], "hi", "body", {"x": "y"})
    assert resp_multi["success"] == 2
    resp_topic = firebase_config.send_topic_notification("topic", "t", "b", {"k": "v"})
    assert resp_topic == "msg-id"
    resp_push = firebase_config.send_push_notification("tok", "h", "b", {"a": "b"})
    assert resp_push == "msg-id"

    assert ("multicast", ["t1", "t2"], {"x": "y"}) in dummy.sent
    assert ("single", "topic", {"k": "v"}) in dummy.sent
    assert ("single", "tok", {"a": "b"}) in dummy.sent

    resp_sub = firebase_config.subscribe_to_topic(["a", "b"], "topic1")
    resp_unsub = firebase_config.unsubscribe_from_topic(["a"], "topic1")
    assert resp_sub["success"] == 2
    assert resp_unsub["success"] == 1
    assert dummy.topic_subs == [(("a", "b"), "topic1")]
    assert dummy.topic_unsubs == [(("a",), "topic1")]


def test_messaging_errors_return_none(monkeypatch):
    class Err:
        def __init__(self, exc):
            self.exc = exc

        def __call__(self, *a, **k):
            raise self.exc

    monkeypatch.setattr(firebase_config, "messaging", type("M", (), {
        "MulticastMessage": firebase_config.messaging.MulticastMessage,
        "Notification": firebase_config.messaging.Notification,
        "Message": firebase_config.messaging.Message,
        "send_multicast": Err(RuntimeError("multi")),
        "send": Err(RuntimeError("send")),
        "subscribe_to_topic": Err(RuntimeError("sub")),
        "unsubscribe_from_topic": Err(RuntimeError("unsub")),
    })())
    monkeypatch.setattr(firebase_config, "logger", type("L", (), {"error": lambda *a, **k: None})())

    assert firebase_config.send_multicast_notification(["t"], "a", "b") is None
    assert firebase_config.send_topic_notification("top", "a", "b") is None
    assert firebase_config.send_push_notification("tok", "a", "b") is None
    assert firebase_config.subscribe_to_topic(["t"], "topic") is None
    assert firebase_config.unsubscribe_from_topic(["t"], "topic") is None


def test_storage_utils_success_and_failure(monkeypatch):
    actions = []

    class DummyBlob:
        def __init__(self, name):
            self.name = name

        def upload_from_filename(self, path):
            actions.append(("upload", self.name, path))

        def generate_signed_url(self, ttl):
            actions.append(("signed", self.name, ttl))
            return f"https://example.com/{self.name}?ttl={ttl}"

        def delete(self):
            actions.append(("delete", self.name))

    class DummyBucket:
        def __init__(self, fail=False):
            self.fail = fail

        def blob(self, name):
            if self.fail:
                raise RuntimeError("boom")
            return DummyBlob(name)

    class DummyStorage:
        def __init__(self, fail=False):
            self.fail = fail

        def bucket(self, name):
            actions.append(("bucket", name))
            return DummyBucket(fail=self.fail)

    # Success paths
    monkeypatch.setattr(firebase_config, "storage", DummyStorage())
    monkeypatch.setattr(firebase_config, "logger", type("L", (), {"error": lambda *a, **k: None})())

    assert firebase_config.upload_file_to_bucket("bkt", "src.txt", "dest.txt") is True
    url = firebase_config.generate_signed_url("bkt", "dest.txt", expires_in_seconds=123)
    assert url.endswith("dest.txt?ttl=123")
    assert firebase_config.delete_file_from_bucket("bkt", "dest.txt") is True

    # Failure paths return graceful fallbacks
    monkeypatch.setattr(firebase_config, "storage", DummyStorage(fail=True))
    assert firebase_config.upload_file_to_bucket("bkt", "src.txt", "dest.txt") is False
    assert firebase_config.generate_signed_url("bkt", "dest.txt") is None
    assert firebase_config.delete_file_from_bucket("bkt", "dest.txt") is False
