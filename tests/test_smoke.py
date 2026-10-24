import socket

import anthropic
import pytest
from typer.testing import CliRunner

from docqa.cli import app
from tests.conftest import NetworkBlockedError


def test_help_runs() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "docqa" in result.output.lower() or "usage" in result.output.lower()


def test_conftest_blocks_real_client() -> None:
    with pytest.raises(NetworkBlockedError):
        anthropic.Anthropic()


def test_conftest_blocks_sockets() -> None:
    with pytest.raises(NetworkBlockedError):
        socket.create_connection(("example.com", 443))
