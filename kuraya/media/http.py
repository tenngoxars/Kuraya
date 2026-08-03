# -*- coding: utf-8 -*-
"""网络请求。UA、超时与重试集中在这里。"""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

TIMEOUT = (10, 30)

_RETRY = Retry(
    total=2,
    backoff_factor=0.5,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset({'GET', 'HEAD'}),
    raise_on_status=False,
)

_MEASURE_CAP = 1 << 20


class Unavailable(Exception):
    """网络请求失败"""


def _session() -> requests.Session:
    session = requests.Session()
    session.headers['User-Agent'] = USER_AGENT
    adapter = HTTPAdapter(max_retries=_RETRY)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    return session


_SESSION = _session()


def get(url: str, headers: dict | None = None, cookies: dict | None = None) -> str:
    """取网页文本。非 200 返回空串，由调用方判为查不到"""
    response = _request(url, headers, cookies)
    if response.status_code != 200:
        return ''
    return response.text


def get_bytes(url: str, headers: dict | None = None) -> bytes:
    """取二进制内容。取不到即抛 Unavailable"""
    response = _request(url, headers)
    if response.status_code != 200:
        raise Unavailable(f'{response.status_code} {url}')
    return response.content


def head_size(url: str, headers: dict | None = None) -> int:
    """
    量一个 URL 的内容体积，取不到返回 0。

    DMM 对不存在的图返回约 2KB 的占位图而不是 404，只能按体积分辨。
    用 GET + stream 不读正文，代价与 HEAD 相当而兼容性更好。
    """
    try:
        with _SESSION.get(url, headers=headers or None, timeout=TIMEOUT,
                          stream=True) as response:
            if response.status_code != 200:
                return 0
            declared = response.headers.get('Content-Length')
            if declared and declared.isdigit():
                return int(declared)
            size = 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size >= _MEASURE_CAP:
                    break
            return size
    except requests.RequestException:
        return 0


def _request(url, headers=None, cookies=None):
    try:
        return _SESSION.get(url, headers=headers or None, cookies=cookies,
                            timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise Unavailable(f'{type(exc).__name__}: {url}') from exc
