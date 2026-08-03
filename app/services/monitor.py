from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.cache import (
    update_api_cache,
    update_system_cache,
)
from app.services.api_checker import check_account_api
from app.services.ssh_checker import collect_system_metrics


def check_single_server_api(
    server: dict[str, Any],
) -> dict[str, Any]:
    result = check_account_api(server)

    update_api_cache(
        server_id=server["id"],
        result=result,
    )

    return {
        "server_id": server["id"],
        "server_name": server["name"],
        "result": result,
    }


def check_single_server_system(
    server: dict[str, Any],
) -> dict[str, Any]:
    result = collect_system_metrics(server)

    update_system_cache(
        server_id=server["id"],
        result=result,
    )

    return {
        "server_id": server["id"],
        "server_name": server["name"],
        "result": result,
    }


def run_checks_concurrently(
    servers: list[dict[str, Any]],
    check_function,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    with ThreadPoolExecutor(
        max_workers=max(len(servers), 1)
    ) as executor:
        future_to_server = {
            executor.submit(
                check_function,
                server,
            ): server
            for server in servers
        }

        for future in as_completed(future_to_server):
            server = future_to_server[future]

            try:
                results.append(future.result())

            except Exception as exception:
                results.append(
                    {
                        "server_id": server["id"],
                        "server_name": server["name"],
                        "error": str(exception),
                    }
                )

    return results


def check_all_server_apis(
    servers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return run_checks_concurrently(
        servers,
        check_single_server_api,
    )


def check_all_server_systems(
    servers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return run_checks_concurrently(
        servers,
        check_single_server_system,
    )


def check_single_server_all(
    server: dict[str, Any],
) -> dict[str, Any]:
    api_result = check_single_server_api(server)
    system_result = check_single_server_system(server)

    return {
        "server_id": server["id"],
        "server_name": server["name"],
        "api": api_result["result"],
        "system": system_result["result"],
    }


def check_all_servers(
    servers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return run_checks_concurrently(
        servers,
        check_single_server_all,
    )