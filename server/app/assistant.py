"""Natural-language payment intents.

Model-first, rules-second: if an OpenAI-compatible endpoint is configured the
text goes to the model; if the call fails, returns junk, or no key is set, the
deterministic parser takes over. The response says which one answered, so a
demo never silently pretends an LLM was involved.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Optional

import httpx

AMOUNT_RE = re.compile(r"\$\s*(\d{1,7}(?:\.\d{1,2})?)")
BARE_AMOUNT_RE = re.compile(r"(?<![\d.])(\d{1,7}(?:\.\d{1,2})?)(?![\d.])")
TOKEN_RE = re.compile(r"\b\d{48}\b")

SYSTEM_PROMPT = """You extract exactly one payment intent for a demo wallet.
Reply with JSON only, no prose, using this shape:
{"action":"PAY"|"UNKNOWN","receiver_name":string|null,"amount_cents":integer|null,"memo":string|null,"confidence":number}
Rules:
- receiver_name MUST come from the provided peers list; never invent a peer.
- amount_cents is an integer number of cents (e.g. $25.00 -> 2500).
- If the recipient or the amount is ambiguous, use action UNKNOWN.
"""


@dataclass(frozen=True)
class ParsedIntent:
    action: str
    receiver_name: Optional[str]
    token48: Optional[str]
    amount_cents: Optional[int]
    memo: Optional[str]
    confidence: float
    source: str
    explanation: str


def _dollars_to_cents(raw: str) -> Optional[int]:
    try:
        value = Decimal(raw.replace(",", "."))
    except InvalidOperation:
        return None
    cents = int((value * 100).quantize(Decimal("1")))
    if 1 <= cents <= 10_000_000:
        return cents
    return None


def extract_amount_cents(text: str) -> Optional[int]:
    match = AMOUNT_RE.search(text) or BARE_AMOUNT_RE.search(text)
    if match is None:
        return None
    return _dollars_to_cents(match.group(1))


def parse_rules(text: str, peers: Iterable[Any]) -> ParsedIntent:
    peer_list = list(peers)
    lower = text.lower()

    token_match = TOKEN_RE.search(text)
    peer = None
    if token_match is not None:
        peer = next(
            (p for p in peer_list if p.token48 == token_match.group(0)), None
        )
    if peer is None:
        peer = next(
            (p for p in peer_list if p.name and p.name.lower() in lower), None
        )

    amount = extract_amount_cents(text)

    if peer is None or amount is None:
        missing = []
        if peer is None:
            missing.append("a known recipient")
        if amount is None:
            missing.append("an amount")
        return ParsedIntent(
            action="UNKNOWN",
            receiver_name=peer.name if peer else None,
            token48=peer.token48 if peer else None,
            amount_cents=amount,
            memo=None,
            confidence=0.3,
            source="rules",
            explanation="Could not find " + " and ".join(missing) + ".",
        )

    return ParsedIntent(
        action="PAY",
        receiver_name=peer.name,
        token48=peer.token48,
        amount_cents=amount,
        memo=None,
        confidence=0.55,
        source="rules",
        explanation=(
            f"Matched {peer.name} in your peer list and read {amount} cents "
            f"from the message."
        ),
    )


class PaymentAssistant:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = 20.0,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.transport = transport

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def parse(self, text: str, peers: Iterable[Any]) -> ParsedIntent:
        peer_list = list(peers)
        if self.configured:
            try:
                intent = await self._model(text, peer_list)
                if intent is not None:
                    return intent
            except Exception:
                # Any model failure is non-fatal: rules still answer.
                pass
        return parse_rules(text, peer_list)

    async def _model(self, text: str, peers: list[Any]) -> Optional[ParsedIntent]:
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "text": text,
                            "peers": [{"name": p.name, "token48": p.token48} for p in peers],
                        }
                    ),
                },
            ],
        }
        async with httpx.AsyncClient(
            timeout=self.timeout, transport=self.transport
        ) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if response.status_code >= 400:
            return None

        content = response.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
        action = str(data.get("action", "UNKNOWN")).upper()

        peer = self._resolve_peer(data, peers)
        amount = data.get("amount_cents")
        try:
            amount_cents = int(amount) if amount is not None else None
        except (TypeError, ValueError):
            amount_cents = None
        if amount_cents is not None and not (1 <= amount_cents <= 10_000_000):
            amount_cents = None

        confidence = data.get("confidence", 0.9)
        try:
            confidence_value = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence_value = 0.9

        if action != "PAY" or peer is None or amount_cents is None:
            return ParsedIntent(
                action="UNKNOWN",
                receiver_name=peer.name if peer else None,
                token48=peer.token48 if peer else None,
                amount_cents=amount_cents,
                memo=None,
                confidence=confidence_value,
                source="model",
                explanation="The model could not map this to one known peer and amount.",
            )

        return ParsedIntent(
            action="PAY",
            receiver_name=peer.name,
            token48=peer.token48,
            amount_cents=amount_cents,
            memo=(data.get("memo") or None),
            confidence=confidence_value,
            source="model",
            explanation=f"{self.model} mapped the request to {peer.name}.",
        )

    @staticmethod
    def _resolve_peer(data: dict, peers: list[Any]) -> Optional[Any]:
        token = data.get("token48")
        if isinstance(token, str):
            match = next((p for p in peers if p.token48 == token), None)
            if match is not None:
                return match
        name = data.get("receiver_name")
        if isinstance(name, str) and name.strip():
            target = name.strip().lower()
            exact = next((p for p in peers if p.name.lower() == target), None)
            if exact is not None:
                return exact
            return next((p for p in peers if target in p.name.lower()), None)
        return None
