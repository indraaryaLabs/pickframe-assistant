from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from pickframe_assistant import Assistant
from pickframe_assistant.llm import LLMConfig, LLMError, OpenAICompatibleGenerator


class _Handler(BaseHTTPRequestHandler):
    reply: Any = "Pro costs Rp 69.000 per month [2]."
    status = 200
    seen: list[dict[str, Any]] = []  # noqa: RUF012

    def do_POST(self) -> None:
        length = int(self.headers["Content-Length"])
        type(self).seen.append(
            {
                "path": self.path,
                "auth": self.headers["Authorization"],
                "body": json.loads(self.rfile.read(length)),
            }
        )
        payload: Any = {"choices": [{"message": {"content": type(self).reply}}]}
        if type(self).reply is None:
            payload = {"unexpected": True}
        self.send_response(type(self).status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def log_message(self, *args: object) -> None:
        return


@pytest.fixture
def server() -> Iterator[str]:
    _Handler.seen = []
    _Handler.status = 200
    _Handler.reply = "Pro costs Rp 69.000 per month [2]."
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}/v1"
    httpd.shutdown()
    thread.join()


def _assistant(base: Assistant, url: str) -> Assistant:
    generator = OpenAICompatibleGenerator(LLMConfig(url, "secret", "test-model", timeout=5))
    return Assistant(base.corpus, generator=generator)


def test_the_environment_configures_the_endpoint() -> None:
    config = LLMConfig.from_env(
        {
            "PICKFRAME_LLM_BASE_URL": "https://example.test/v1/",
            "PICKFRAME_LLM_API_KEY": "k",
            "PICKFRAME_LLM_MODEL": "m",
        }
    )
    assert (config.base_url, config.api_key, config.model) == ("https://example.test/v1", "k", "m")


def test_missing_settings_are_named(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("PICKFRAME_LLM_BASE_URL", "PICKFRAME_LLM_API_KEY", "PICKFRAME_LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(LLMError, match="PICKFRAME_LLM_BASE_URL, PICKFRAME_LLM_API_KEY"):
        LLMConfig.from_env()


def test_a_cited_reply_becomes_an_answer_with_renumbered_citations(
    assistant: Assistant, server: str
) -> None:
    answer = _assistant(assistant, server).answer("How much is the Pro plan per month?")
    assert answer.kind == "answer"
    assert answer.text.endswith("[1].")
    assert len(answer.citations) == 1
    request = _Handler.seen[0]
    assert request["path"] == "/v1/chat/completions"
    assert request["auth"] == "Bearer secret"
    assert request["body"]["model"] == "test-model"
    assert request["body"]["temperature"] == 0
    assert (
        "Question: How much is the Pro plan per month?" in request["body"]["messages"][1]["content"]
    )
    assert "Reply in English" in request["body"]["messages"][0]["content"]


def test_the_model_can_decline(assistant: Assistant, server: str) -> None:
    _Handler.reply = "NO_ANSWER"
    assert (
        _assistant(assistant, server).answer("How much is the Pro plan per month?").kind
        == "abstain"
    )


def test_a_reply_without_a_citation_is_not_an_answer(assistant: Assistant, server: str) -> None:
    _Handler.reply = "Pro costs Rp 69.000 per month."
    assert (
        _assistant(assistant, server).answer("How much is the Pro plan per month?").kind
        == "abstain"
    )


def test_a_citation_to_a_passage_that_was_not_given_is_ignored(
    assistant: Assistant, server: str
) -> None:
    _Handler.reply = "Pro costs Rp 69.000 per month [9]."
    assert (
        _assistant(assistant, server).answer("How much is the Pro plan per month?").kind
        == "abstain"
    )


def test_an_empty_reply_is_not_an_answer(assistant: Assistant, server: str) -> None:
    _Handler.reply = "   "
    assert (
        _assistant(assistant, server).answer("How much is the Pro plan per month?").kind
        == "abstain"
    )


@pytest.mark.parametrize("status", [500, 401])
def test_http_errors_are_reported(assistant: Assistant, server: str, status: int) -> None:
    _Handler.status = status
    with pytest.raises(LLMError, match="endpoint failed"):
        _assistant(assistant, server).answer("How much is the Pro plan per month?")


def test_an_unexpected_payload_is_reported(assistant: Assistant, server: str) -> None:
    _Handler.reply = None
    with pytest.raises(LLMError, match="endpoint failed"):
        _assistant(assistant, server).answer("How much is the Pro plan per month?")


def test_an_unreachable_endpoint_is_reported(assistant: Assistant) -> None:
    with pytest.raises(LLMError, match="endpoint failed"):
        _assistant(assistant, "http://127.0.0.1:9/v1").answer("How much is the Pro plan per month?")
