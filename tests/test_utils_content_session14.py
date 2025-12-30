from app.modules.utils import content as utils_content


def test_use_lightweight_nlp_stub(monkeypatch):
    monkeypatch.setattr(utils_content.settings, "environment", "test")
    monkeypatch.setenv("LIGHTWEIGHT_NLP", "1")

    clf = utils_content._get_offensive_classifier()
    sent = utils_content._get_sentiment_pipeline()

    assert clf("text")[0]["label"] == "LABEL_0"
    assert sent("text")[0]["label"] == "POSITIVE"


def test_check_content_against_rules_matches_regex():
    rules = [r"bad\d+", r"foo"]
    assert utils_content.check_content_against_rules("bad123", rules) is False
    assert utils_content.check_content_against_rules("other", rules) is True


def test_train_content_classifier_runs(monkeypatch, tmp_path):
    monkeypatch.setattr(
        utils_content.joblib,
        "dump",
        lambda obj, path: __import__("pathlib").Path(path).write_bytes(b"1"),
    )
    monkeypatch.setattr(utils_content, "profanity", type("P", (), {"load_censor_words": lambda: None}))
    monkeypatch.setattr(utils_content, "stopwords", type("S", (), {"words": lambda lang: ["a", "b"]}))
    monkeypatch.setattr(utils_content, "CountVectorizer", utils_content.CountVectorizer)
    monkeypatch.setattr(utils_content, "MultinomialNB", utils_content.MultinomialNB)

    # Work in temp directory so files are written there.
    monkeypatch.chdir(tmp_path)

    utils_content.train_content_classifier()
    assert (tmp_path / "content_classifier.joblib").exists()


def test_detect_language_handles_exception(monkeypatch):
    def boom(text):
        raise utils_content.LangDetectException("fail", None)

    monkeypatch.setattr(utils_content, "detect", boom)
    assert utils_content.detect_language("x") == "unknown"


def test_embed_sentiment_pipeline_real(monkeypatch):
    # Force lightweight stub to avoid heavy model load
    monkeypatch.setenv("LIGHTWEIGHT_NLP", "1")
    monkeypatch.setattr(utils_content.settings, "environment", "test")
    pipe = utils_content._get_sentiment_pipeline()
    result = pipe("hello")[0]
    assert result["label"] == "POSITIVE"
    assert "score" in result
