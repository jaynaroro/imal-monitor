from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.services.api_checker import check_account_api
from app.services.ssh_checker import execute_ssh_command


logger = logging.getLogger(__name__)

NAIROBI_TIMEZONE = ZoneInfo("Africa/Nairobi")


def current_timestamp() -> str:
    return datetime.now(
        NAIROBI_TIMEZONE
    ).isoformat(timespec="seconds")


def get_control_config(
    server: dict[str, Any],
) -> dict[str, Any]:
    control = server.get(
        "application_control",
        {},
    )

    if not control.get("enabled", False):
        raise ValueError(
            f"Application control is disabled for "
            f"{server['name']}"
        )

    required_fields = {
        "tomcat_home",
        "process_match",
    }

    missing = required_fields - control.keys()

    if missing:
        raise ValueError(
            "Missing Tomcat control settings: "
            + ", ".join(sorted(missing))
        )

    return control


def get_tomcat_pids(
    server: dict[str, Any],
) -> list[int]:
    control = get_control_config(server)

    process_match = control["process_match"]

    command = (
        "pgrep -f -- "
        f"'{process_match}' || true"
    )

    stdout, stderr, _ = execute_ssh_command(
        server,
        command,
    )

    pids: list[int] = []

    for line in stdout.splitlines():
        value = line.strip()

        if value.isdigit():
            pids.append(int(value))

    return pids


def wait_for_tomcat_stop(
    server: dict[str, Any],
    timeout: int,
) -> bool:
    deadline = time.time() + timeout

    while time.time() < deadline:
        if not get_tomcat_pids(server):
            return True

        time.sleep(2)

    return False


def wait_for_tomcat_start(
    server: dict[str, Any],
    timeout: int,
) -> bool:
    deadline = time.time() + timeout

    while time.time() < deadline:
        if get_tomcat_pids(server):
            return True

        time.sleep(2)

    return False


def stop_tomcat(
    server: dict[str, Any],
) -> dict[str, Any]:
    control = get_control_config(server)

    tomcat_home = control["tomcat_home"]

    shutdown_timeout = int(
        control.get(
            "shutdown_timeout",
            30,
        )
    )

    pids_before = get_tomcat_pids(server)

    if not pids_before:
        return {
            "stopped": True,
            "already_stopped": True,
            "forced": False,
            "pids_before": [],
        }

    logger.warning(
        "CONTROL | %s | Tomcat shutdown requested | PIDs=%s",
        server["id"],
        pids_before,
    )

    shutdown_command = (
        f"cd '{tomcat_home}/bin' "
        "&& ./shutdown.sh"
    )

    stdout, stderr, exit_code = (
        execute_ssh_command(
            server,
            shutdown_command,
        )
    )

    logger.info(
        "CONTROL | %s | shutdown.sh exit=%s stdout=%s stderr=%s",
        server["id"],
        exit_code,
        stdout.strip(),
        stderr.strip(),
    )

    if wait_for_tomcat_stop(
        server,
        shutdown_timeout,
    ):
        logger.info(
            "CONTROL | %s | Tomcat stopped gracefully",
            server["id"],
        )

        return {
            "stopped": True,
            "already_stopped": False,
            "forced": False,
            "pids_before": pids_before,
        }

    remaining_pids = get_tomcat_pids(server)

    if remaining_pids:
        logger.warning(
            "CONTROL | %s | graceful shutdown timed out | "
            "sending SIGTERM to PIDs=%s",
            server["id"],
            remaining_pids,
        )

        pid_string = " ".join(
            str(pid)
            for pid in remaining_pids
        )

        execute_ssh_command(
            server,
            f"kill {pid_string}",
        )

    if wait_for_tomcat_stop(
        server,
        10,
    ):
        logger.info(
            "CONTROL | %s | Tomcat stopped after SIGTERM",
            server["id"],
        )

        return {
            "stopped": True,
            "already_stopped": False,
            "forced": False,
            "pids_before": pids_before,
        }

    remaining_pids = get_tomcat_pids(server)

    if remaining_pids:
        logger.error(
            "CONTROL | %s | forcing Tomcat shutdown | PIDs=%s",
            server["id"],
            remaining_pids,
        )

        pid_string = " ".join(
            str(pid)
            for pid in remaining_pids
        )

        execute_ssh_command(
            server,
            f"kill -9 {pid_string}",
        )

    if not wait_for_tomcat_stop(
        server,
        10,
    ):
        raise RuntimeError(
            "Tomcat could not be stopped"
        )

    return {
        "stopped": True,
        "already_stopped": False,
        "forced": True,
        "pids_before": pids_before,
    }


def start_tomcat(
    server: dict[str, Any],
) -> dict[str, Any]:
    control = get_control_config(server)

    tomcat_home = control["tomcat_home"]

    startup_timeout = int(
        control.get(
            "startup_timeout",
            60,
        )
    )

    existing_pids = get_tomcat_pids(
        server
    )

    if existing_pids:
        return {
            "started": True,
            "already_running": True,
            "pids": existing_pids,
        }

    logger.warning(
        "CONTROL | %s | starting Tomcat",
        server["id"],
    )

    startup_command = (
        f"cd '{tomcat_home}/bin' "
        "&& ./startup.sh"
    )

    stdout, stderr, exit_code = (
        execute_ssh_command(
            server,
            startup_command,
        )
    )

    logger.info(
        "CONTROL | %s | startup.sh exit=%s stdout=%s stderr=%s",
        server["id"],
        exit_code,
        stdout.strip(),
        stderr.strip(),
    )

    if not wait_for_tomcat_start(
        server,
        startup_timeout,
    ):
        raise RuntimeError(
            "Tomcat did not start within "
            f"{startup_timeout} seconds"
        )

    pids = get_tomcat_pids(server)

    logger.info(
        "CONTROL | %s | Tomcat started | PIDs=%s",
        server["id"],
        pids,
    )

    return {
        "started": True,
        "already_running": False,
        "pids": pids,
    }


def wait_for_api_health(
    server: dict[str, Any],
    timeout: int = 90,
) -> dict[str, Any]:
    deadline = time.time() + timeout

    last_result: dict[str, Any] | None = None

    while time.time() < deadline:
        last_result = check_account_api(
            server
        )

        if last_result.get("healthy"):
            return last_result

        time.sleep(5)

    if last_result is None:
        raise RuntimeError(
            "API health check did not run"
        )

    return last_result


def restart_tomcat(
    server: dict[str, Any],
) -> dict[str, Any]:
    get_control_config(server)

    started_at = current_timestamp()

    logger.warning(
        "CONTROL | %s | restart requested",
        server["id"],
    )

    try:
        stop_result = stop_tomcat(
            server
        )

        start_result = start_tomcat(
            server
        )

        api_result = wait_for_api_health(
            server,
            timeout=90,
        )

        success = bool(
            api_result.get("healthy")
        )

        logger.info(
            "CONTROL | %s | restart completed | api_healthy=%s",
            server["id"],
            success,
        )

        return {
            "success": success,
            "server_id": server["id"],
            "server_name": server["name"],
            "message": (
                "Application restarted successfully"
                if success
                else (
                    "Tomcat started but API health "
                    "check did not return Success"
                )
            ),
            "stop": stop_result,
            "start": start_result,
            "api": {
                "healthy": api_result.get(
                    "healthy"
                ),
                "status_desc": api_result.get(
                    "status_desc"
                ),
                "http_status": api_result.get(
                    "http_status"
                ),
                "response_time_ms": (
                    api_result.get(
                        "response_time_ms"
                    )
                ),
            },
            "started_at": started_at,
            "completed_at": current_timestamp(),
        }

    except Exception as exception:
        logger.exception(
            "CONTROL | %s | restart failed",
            server["id"],
        )

        return {
            "success": False,
            "server_id": server["id"],
            "server_name": server["name"],
            "message": str(exception),
            "started_at": started_at,
            "completed_at": current_timestamp(),
        }
