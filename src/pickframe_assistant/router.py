"""Decides, before any retrieval, whether a question is one the assistant must not answer itself.

Two things are caught here, and both are rules rather than a model so that every decision can be
traced to a named line:

* `refuse`: text that tries to change the assistant's instructions or to put words in its mouth.
* `handoff`: questions about the asker's own account, payment or code, and requests for an action
  only the PickFrame team can take (activate a plan, refund, delete an account).

Questions about how those things work in general ("how do I redeem a code?") are not handed off:
they have an answer in the knowledge base.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Literal

from pickframe_assistant.text import normalise, words


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern[str]
    # A match is ignored when this also matches: it marks a question about how things work.
    unless: re.Pattern[str] | None = None


@dataclass(frozen=True)
class Route:
    kind: Literal["refuse", "handoff"] | None
    rule: str | None = None


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


def _either_order(a: str, b: str, gap: int = 40) -> str:
    return rf"(?:\b(?:{a})\b.{{0,{gap}}}\b(?:{b})\b|\b(?:{b})\b.{{0,{gap}}}\b(?:{a})\b)"


_TROUBLE: Final = (
    r"tidak bisa|tidak dapat|gagal|ditolak|invalid|salah|error|hilang|lupa|terkunci|dikunci|"
    r"diblokir|diretas|dibekukan|cant|cannot|unable|failed|fails|failing|rejected|lost|forgot|"
    r"locked|blocked|hacked|suspended|stuck|broken|wont work|doesnt work|didnt work|not working"
)

REFUSE_RULES: Final[tuple[Rule, ...]] = (
    Rule(
        "override_instructions",
        _rx(
            r"\b(ignore|disregard|forget|override|abaikan|lupakan)\b.{0,40}"
            r"\b(instructions?|rules?|prompts?|guidelines?|instruksi|perintah|aturan|petunjuk)\b"
        ),
    ),
    Rule(
        "reveal_prompt",
        _rx(
            r"\b(system prompt|prompt sistem|developer mode|jailbreak)\b|"
            r"\b(reveal|show|print|repeat|tampilkan|ungkapkan)\b.{0,30}"
            r"\b(your|the|kamu|anda)\b.{0,20}\b(instructions?|prompt|rules|instruksi|aturan)\b|"
            r"\b(tampilkan|ungkapkan)\b.{0,20}\b(instruksi|aturan|prompt)\b.{0,15}\b(kamu|anda)\b"
        ),
    ),
    Rule(
        "role_play",
        _rx(r"\b(pretend|act as|roleplay|you are now|berpura|pura pura|anggap kamu)\b"),
    ),
    Rule(
        "put_words_in_mouth",
        _rx(
            r"\b(say|state|claim|promise|katakan|bilang|nyatakan)\b.{0,12}\b(that|bahwa)\b|"
            r"\b(bilang|katakan)\s+(saja|aja)\b"
        ),
    ),
)

HANDOFF_RULES: Final[tuple[Rule, ...]] = (
    Rule(
        "paid_awaiting_activation",
        _rx(
            r"\b(sudah|telah|already|just)\s+(transfer|transferred|bayar|membayar|paid|pay|sent|"
            r"kirim|mengirim)\b"
        ),
    ),
    Rule("code_problem", _rx(_either_order(r"kode|code", _TROUBLE))),
    Rule(
        "account_problem", _rx(_either_order(r"akun|account|login|log in|password|sandi", _TROUBLE))
    ),
    Rule(
        "refund_request",
        _rx(
            r"\b(minta|mau|ingin|want|need|id like|would like|tolong|please|mohon)\b.{0,25}"
            r"\b(refund|pengembalian|uang kembali|money back)\b"
        ),
        unless=_rx(
            r"\b(cara|syarat|kebijakan|policy|how|bagaimana|apakah|berapa|kapan|when|if|jika|"
            r"bisa|can|could|apa)\b"
        ),
    ),
    Rule(
        "action_request",
        _rx(
            r"\b(tolong|mohon|please|can you|could you|bisa tolong)\b.{0,30}"
            r"\b(aktifkan|activate|extend|perpanjangkan|upgrade|naikkan|hapuskan|delete|reset|"
            r"ubah|change|cancel|batalkan|kembalikan)\b.{0,30}"
            r"\b(akun|account|paket|plan|langganan|subscription|pro|studio|data|password|sandi|"
            r"kode|code)\b"
        ),
    ),
    Rule(
        "own_state_problem",
        _rx(
            r"\b(saya|my|i)\b.{0,50}\b(belum|tidak|gagal|not|didnt|havent|hasnt|isnt|wasnt|arent|doesnt|dont|cant|wont|never)\b.{0,40}"
            r"\b(masuk|diterima|aktif|active|activated|received|working|dibuka|terbuka|muncul|"
            r"showing|appear|appearing|loading|open|opening|login|log in|terkonfirmasi|"
            r"dikonfirmasi|confirmed|diproses|processed)\b"
        ),
    ),
)


def _first_match(text: str, rules: tuple[Rule, ...]) -> str | None:
    for rule in rules:
        if rule.pattern.search(text) and not (rule.unless and rule.unless.search(text)):
            return rule.name
    return None


def route(question: str) -> Route:
    """`refuse` wins over `handoff`: an injected instruction is never worth a human's time."""
    text = " ".join(words(normalise(question)))
    refuse = _first_match(text, REFUSE_RULES)
    if refuse:
        return Route("refuse", refuse)
    handoff = _first_match(text, HANDOFF_RULES)
    if handoff:
        return Route("handoff", handoff)
    return Route(None)
