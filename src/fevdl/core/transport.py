"""HTTPS fuer Code-Downloads, einschliesslich jeder Weiterleitung."""

from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


def _check_url(url: str, hosts: frozenset[str]) -> None:
    try:
        parsed = urlsplit(url)
        valid = (
            parsed.scheme == "https" and parsed.hostname in hosts
            and parsed.port in (None, 443) and parsed.username is None
            and parsed.password is None and not parsed.fragment
            and not any(ord(char) < 33 or char == "\\" for char in url)
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Nicht erlaubte Adresse beim Laden einer Aktualisierung.")


class _CheckedRedirects(HTTPRedirectHandler):
    def __init__(self, hosts: frozenset[str]):
        self.hosts = hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Vor dem naechsten Request pruefen, nicht erst die letzte Antwort.
        _check_url(newurl, self.hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_https(request: Request, timeout: float, hosts: frozenset[str]):
    _check_url(request.full_url, hosts)
    # HTTPSHandler behaelt die Zertifikatspruefung der Standardbibliothek bei.
    return build_opener(_CheckedRedirects(hosts)).open(request, timeout=timeout)
