import socket
import time
from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network

Network = IPv4Network | IPv6Network

RESOLVE_TTL_SECONDS = 30.0


class HostAllowlist:
    def __init__(self, entries: list[str], ttl: float = RESOLVE_TTL_SECONDS) -> None:
        self._names: list[str] = []
        self._networks: list[Network] = []
        self._ttl = ttl
        self._cache: list[Network] = []
        self._cached_at = 0.0

        for entry in entries:
            value = entry.strip()
            if not value:
                continue
            try:
                self._networks.append(ip_network(value, strict=False))
            except ValueError:
                self._names.append(value)

    def is_allowed(self, client_host: str | None) -> bool:
        if client_host is None:
            return False
        try:
            client = ip_address(client_host)
        except ValueError:
            return False

        if any(client in network for network in self._networks):
            return True
        return any(client in network for network in self._resolved_names())

    def _resolved_names(self) -> list[Network]:
        if not self._names:
            return []

        now = time.monotonic()
        if self._cache and now - self._cached_at < self._ttl:
            return self._cache

        resolved: list[Network] = []
        for name in self._names:
            for info in self._safe_getaddrinfo(name):
                resolved.append(ip_network(info, strict=False))

        self._cache = resolved
        self._cached_at = now
        return resolved

    @staticmethod
    def _safe_getaddrinfo(name: str) -> list[str]:
        try:
            infos = socket.getaddrinfo(name, None, proto=socket.IPPROTO_TCP)
        except socket.gaierror:
            return []
        return [str(info[4][0]) for info in infos]
