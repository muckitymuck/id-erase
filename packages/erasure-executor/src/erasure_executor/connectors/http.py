from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx


_BLOCKED_CIDRS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

_ALLOWED_SCHEMES = {"http", "https"}


class SSRFError(ValueError):
    """Raised when a URL targets a blocked internal address."""


def validate_url(url: str) -> str:
    parsed = urlparse(url)

    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise SSRFError(f"URL scheme not allowed: {parsed.scheme!r}")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFError("URL has no hostname")

    try:
        addr = ipaddress.ip_address(hostname)
        _check_ip(addr)
    except ValueError:
        try:
            addrinfos = socket.getaddrinfo(hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            raise SSRFError(f"DNS resolution failed for {hostname!r}: {exc}") from exc
        for _family, _type, _proto, _canonname, sockaddr in addrinfos:
            ip = ipaddress.ip_address(sockaddr[0])
            _check_ip(ip)

    return url


def _check_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    for cidr in _BLOCKED_CIDRS:
        if ip in cidr:
            raise SSRFError(f"URL resolves to blocked address: {ip}")


@dataclass(frozen=True)
class HttpResult:
    status_code: int
    headers: dict[str, str]
    text: str
    json: Any | None


class HttpConnector:
    def __init__(self, timeout_ms: int, *, skip_ssrf_check: bool = False):
        self._timeout = timeout_ms / 1000.0
        self._skip_ssrf_check = skip_ssrf_check

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        json_body: Any | None = None,
    ) -> HttpResult:
        if not self._skip_ssrf_check:
            validate_url(url)

        def _on_redirect(response: httpx.Response) -> None:
            if not self._skip_ssrf_check and response.next_request:
                validate_url(str(response.next_request.url))

        event_hooks: dict[str, list] = {"response": [_on_redirect]}
        with httpx.Client(
            timeout=self._timeout,
            follow_redirects=True,
            event_hooks=event_hooks,
        ) as client:
            res = client.request(method.upper(), url, headers=headers, params=params, json=json_body)
            try:
                js = res.json()
            except Exception:
                js = None
            return HttpResult(
                status_code=res.status_code,
                headers=dict(res.headers),
                text=res.text,
                json=js,
            )
