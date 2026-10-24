"""Static and HTTP checks for the sample widget (ADR 0006, AC8)."""

import base64
import hashlib
import re
from html.parser import HTMLParser
from importlib.resources import files

from fastapi.testclient import TestClient

from docqa import api

WIDGET = files("docqa").joinpath("static/index.html").read_text("utf-8")


class Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.inline: dict[str, list[str]] = {"script": [], "style": []}
        self.attrs: list[tuple[str, str, str | None]] = []
        self._current: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            self.attrs.append((tag, name, value))
            if name == "id" and value:
                self.ids.add(value)
        if tag in self.inline:
            self._current = tag
            self.inline[tag].append("")

    def handle_endtag(self, tag: str) -> None:
        if tag == self._current:
            self._current = None

    def handle_data(self, data: str) -> None:
        if self._current:
            self.inline[self._current][-1] += data


def parsed() -> Collector:
    collector = Collector()
    collector.feed(WIDGET)
    return collector


def sha(text: str) -> str:
    return base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode()


def test_single_inline_script_and_style() -> None:
    c = parsed()
    assert len(c.inline["script"]) == 1
    assert len(c.inline["style"]) == 1
    assert not any(tag == "script" and name == "src" for tag, name, _ in c.attrs)


def test_no_dangerous_dom_apis() -> None:
    for banned in (
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "document.write",
        "eval(",
        "new Function",
    ):
        assert banned not in WIDGET, banned
    assert not re.search(r"setTimeout\(\s*['\"`]", WIDGET)
    assert "textContent" in WIDGET
    assert 'fetch("/chat"' in WIDGET


def test_no_inline_handlers_or_external_urls() -> None:
    c = parsed()
    assert not [name for _, name, _ in c.attrs if name.startswith("on")]
    for _, name, value in c.attrs:
        if name in {"src", "href"}:
            assert not re.match(r"https?://", value or "")
    assert not re.search(r"https?://", WIDGET)


def test_every_element_id_used_by_script_exists() -> None:
    c = parsed()
    used = set(re.findall(r'getElementById\("([^"]+)"\)', c.inline["script"][0]))
    assert used, "script should look up its elements by id"
    assert used <= c.ids


def test_history_cap_matches_server_default() -> None:
    assert re.search(r"MAX_MESSAGES\s*=\s*20\b", WIDGET)


def test_get_root_serves_widget_with_strict_headers() -> None:
    with TestClient(api.app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert response.text == WIDGET
    csp = response.headers["content-security-policy"]
    c = parsed()
    assert f"script-src 'sha256-{sha(c.inline['script'][0])}'" in csp
    assert f"style-src 'sha256-{sha(c.inline['style'][0])}'" in csp
    for directive in (
        "default-src 'none'",
        "connect-src 'self'",
        "img-src 'self'",
        "base-uri 'none'",
        "form-action 'none'",
        "frame-ancestors 'self'",
    ):
        assert directive in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_inline_hash_requires_the_tag() -> None:
    import pytest

    with pytest.raises(RuntimeError, match="no inline <script>"):
        api._inline_hash("<html></html>", "script")
