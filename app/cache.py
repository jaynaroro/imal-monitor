from copy import deepcopy
from threading import Lock
from typing import Any, Optional


_cache_lock = Lock()

_monitor_cache: dict[str, dict[str, Any]] = {}


def initialize_cache(
    servers: list[dict[str, Any]],
) -> None:
    with _cache_lock:
        for server in servers:
            server_id = server["id"]

            if server_id not in _monitor_cache:
                _monitor_cache[server_id] = {
                    "id": server_id,
                    "name": server["name"],
                    "api": {
                        "status": "pending",
                        "healthy": None,
                        "status_desc": None,
                        "http_status": None,
                        "response_time_ms": None,
                        "error": None,
                        "checked_at": None,
                    },
                    "system": {
                        "status": "pending",
                        "healthy": None,
                        "ssh_status": "pending",
                        "cpu": None,
                        "memory": None,
                        "filesystems": [],
                        "highest_filesystem": None,
                        "load_average": None,
                        "uptime": None,
                        "response_time_ms": None,
                        "error": None,
                        "checked_at": None,
                    },
                }


def update_api_cache(
    server_id: str,
    result: dict[str, Any],
) -> None:
    with _cache_lock:
        if server_id not in _monitor_cache:
            raise KeyError(
                f"Server '{server_id}' is not initialized"
            )

        _monitor_cache[server_id]["api"] = result


def get_cache() -> dict[str, dict[str, Any]]:
    with _cache_lock:
        return deepcopy(_monitor_cache)


def get_server_cache(
    server_id: str,
) -> Optional[dict[str, Any]]:
    with _cache_lock:
        server = _monitor_cache.get(server_id)

        if server is None:
            return None

        return deepcopy(server)


def update_system_cache(
    server_id: str,
    result: dict[str, Any],
) -> None:
    with _cache_lock:
        if server_id not in _monitor_cache:
            raise KeyError(
                f"Server '{server_id}' is not initialized"
            )

        _monitor_cache[server_id]["system"] = result
