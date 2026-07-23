import requests


def mk_https_session(pool_maxsize: int) -> requests.Session:
    """Session con keep-alive + pool de conexiones. Reduce SSLEOF/EOF en Windows
    al evitar crear miles de handshakes en paralelo."""
    try:
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
    except Exception:
        return requests.Session()

    s = requests.Session()
    retry = Retry(
        total=0,
        connect=0,
        read=0,
        redirect=0,
        status=0,
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(
        pool_connections=max(1, pool_maxsize),
        pool_maxsize=max(1, pool_maxsize),
        max_retries=retry,
        pool_block=True,
    )
    s.mount("https://", adapter)
    return s
