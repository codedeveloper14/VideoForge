from src.core.config import Config


def test_session_cookie_secure_false_en_http():
    c = Config(public_base_url="http://localhost:8080")
    assert c.session_cookie_secure is False


def test_session_cookie_secure_true_en_https():
    c = Config(public_base_url="https://api.videoforge.example")
    assert c.session_cookie_secure is True
