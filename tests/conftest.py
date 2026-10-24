"""Shared fixtures. Guarantees that no test can reach the real Anthropic API or the network."""

from __future__ import annotations

import socket
from typing import Any

import anthropic
import pytest


class NetworkBlockedError(RuntimeError):
    """Raised when a test tries to open a real network connection."""


def _refuse_client(*_args: Any, **_kwargs: Any) -> Any:
    raise NetworkBlockedError("Tests must not create a real anthropic.Anthropic client")


def _refuse_connect(*_args: Any, **_kwargs: Any) -> Any:
    raise NetworkBlockedError("Tests must not open network connections")


@pytest.fixture(autouse=True)
def _no_real_api(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove the API key and make any real client construction or socket connect fail loudly."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(anthropic, "Anthropic", _refuse_client)
    monkeypatch.setattr(socket.socket, "connect", _refuse_connect)
    monkeypatch.setattr(socket, "create_connection", _refuse_connect)
