import socket

import pytest

from app.utils.network import HostAllowlist


def test_exact_ip_is_allowed() -> None:
    allowlist = HostAllowlist(["172.19.0.4"])

    assert allowlist.is_allowed("172.19.0.4")
    assert not allowlist.is_allowed("172.19.0.5")


def test_cidr_range_is_allowed() -> None:
    allowlist = HostAllowlist(["172.19.0.0/24"])

    assert allowlist.is_allowed("172.19.0.7")
    assert not allowlist.is_allowed("172.20.0.7")


def test_docker_gateway_is_not_allowed_by_container_entry() -> None:
    allowlist = HostAllowlist(["172.19.0.4"])

    assert not allowlist.is_allowed("172.19.0.1")


def test_empty_allowlist_denies_everything() -> None:
    allowlist = HostAllowlist([])

    assert not allowlist.is_allowed("127.0.0.1")


def test_missing_client_address_is_denied() -> None:
    allowlist = HostAllowlist(["127.0.0.1"])

    assert not allowlist.is_allowed(None)


def test_garbage_client_address_is_denied() -> None:
    allowlist = HostAllowlist(["127.0.0.1"])

    assert not allowlist.is_allowed("nije-adresa")


def test_hostname_is_resolved(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(host: str, *args: object, **kwargs: object) -> list[object]:
        assert host == "mosquitto"
        return [(2, 1, 6, "", ("172.19.0.4", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    allowlist = HostAllowlist(["mosquitto"])

    assert allowlist.is_allowed("172.19.0.4")
    assert not allowlist.is_allowed("172.19.0.1")


def test_unresolvable_hostname_denies_instead_of_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_getaddrinfo(*args: object, **kwargs: object) -> list[object]:
        raise socket.gaierror("ime se ne razresava")

    monkeypatch.setattr(socket, "getaddrinfo", failing_getaddrinfo)
    allowlist = HostAllowlist(["mosquitto"])

    assert not allowlist.is_allowed("172.19.0.4")


def test_resolution_is_cached_within_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def counting_getaddrinfo(*args: object, **kwargs: object) -> list[object]:
        nonlocal calls
        calls += 1
        return [(2, 1, 6, "", ("172.19.0.4", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", counting_getaddrinfo)
    allowlist = HostAllowlist(["mosquitto"], ttl=60.0)

    allowlist.is_allowed("172.19.0.4")
    allowlist.is_allowed("172.19.0.4")

    assert calls == 1


def test_new_container_address_is_picked_up_after_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    address = "172.19.0.4"

    def moving_getaddrinfo(*args: object, **kwargs: object) -> list[object]:
        return [(2, 1, 6, "", (address, 0))]

    monkeypatch.setattr(socket, "getaddrinfo", moving_getaddrinfo)
    allowlist = HostAllowlist(["mosquitto"], ttl=0.0)

    assert allowlist.is_allowed("172.19.0.4")
    address = "172.19.0.9"
    assert allowlist.is_allowed("172.19.0.9")
    assert not allowlist.is_allowed("172.19.0.4")


def test_names_and_networks_can_be_mixed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("172.19.0.4", 0))],
    )
    allowlist = HostAllowlist(["mosquitto", "10.0.0.0/8"])

    assert allowlist.is_allowed("172.19.0.4")
    assert allowlist.is_allowed("10.1.2.3")
    assert not allowlist.is_allowed("192.168.1.5")
