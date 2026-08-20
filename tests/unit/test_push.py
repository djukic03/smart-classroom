import json
from typing import Any

import httpx
import pytest

from app.core import push as push_module
from app.core.push import ConsolePushSender, ExpoPushSender, PushMessage

TOKEN_A = "ExponentPushToken[aaaaaaaaaaaaaaaaaaaaaa]"
TOKEN_B = "ExponentPushToken[bbbbbbbbbbbbbbbbbbbbbb]"


def message(token: str) -> PushMessage:
    return PushMessage(token=token, title="CO2", body="1500 ppm", data={"id": 1})


def install_transport(
    monkeypatch: pytest.MonkeyPatch, handler: Any
) -> list[list[dict[str, Any]]]:
    """Presrece HTTP sloj i belezi telo svakog zahteva."""
    seen: list[list[dict[str, Any]]] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return handler(request)

    # Prava klasa se hvata pre patch-a -- inace fabrika poziva samu sebe.
    real_client = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        return real_client(transport=httpx.MockTransport(wrapped))

    monkeypatch.setattr(push_module.httpx, "AsyncClient", factory)
    return seen


def tickets(*statuses: dict[str, Any]) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": list(statuses)})

    return handler


async def test_console_sender_reports_no_dead_tokens() -> None:
    assert await ConsolePushSender().send([message(TOKEN_A)]) == []


async def test_console_sender_handles_empty_list() -> None:
    assert await ConsolePushSender().send([]) == []


async def test_successful_send_reports_no_dead_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transport(monkeypatch, tickets({"status": "ok"}))

    assert await ExpoPushSender().send([message(TOKEN_A)]) == []


async def test_unregistered_device_token_is_reported_dead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transport(
        monkeypatch,
        tickets(
            {"status": "ok"},
            {
                "status": "error",
                "message": "not registered",
                "details": {"error": "DeviceNotRegistered"},
            },
        ),
    )

    dead = await ExpoPushSender().send([message(TOKEN_A), message(TOKEN_B)])

    assert dead == [TOKEN_B]


async def test_other_ticket_errors_do_not_delete_the_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Privremena greska ne sme da obrise ispravan token."""
    install_transport(
        monkeypatch,
        tickets(
            {
                "status": "error",
                "message": "too many requests",
                "details": {"error": "MessageRateExceeded"},
            }
        ),
    )

    assert await ExpoPushSender().send([message(TOKEN_A)]) == []


async def test_failed_request_raises_so_the_worker_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    install_transport(monkeypatch, handler)

    with pytest.raises(httpx.HTTPStatusError):
        await ExpoPushSender().send([message(TOKEN_A)])


async def test_messages_are_split_into_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(push_module.settings, "expo_push_batch_size", 2)
    seen = install_transport(monkeypatch, tickets({"status": "ok"}, {"status": "ok"}))

    await ExpoPushSender().send([message(f"token-{i}") for i in range(5)])

    assert [len(batch) for batch in seen] == [2, 2, 1]


async def test_request_body_matches_the_expo_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = install_transport(monkeypatch, tickets({"status": "ok"}))

    await ExpoPushSender().send([message(TOKEN_A)])

    assert seen[0] == [
        {
            "to": TOKEN_A,
            "title": "CO2",
            "body": "1500 ppm",
            "data": {"id": 1},
        }
    ]


async def test_empty_message_list_does_not_call_the_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = install_transport(monkeypatch, tickets())

    assert await ExpoPushSender().send([]) == []
    assert seen == []
