"""Link-Eingaben an der Grenze zum Download-Motor pruefen."""

from urllib.parse import urlsplit


def web_url(value: str) -> str:
    url = (value or "").strip()
    try:
        parsed = urlsplit(url)
        valid = (parsed.scheme in ("http", "https") and bool(parsed.hostname)
                 and (parsed.port is None or 1 <= parsed.port <= 65535))
        if any(ord(c) < 33 or c == "\\" for c in url):
            valid = False
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Bitte einen vollstaendigen http- oder https-Link einfuegen.")
    return url
