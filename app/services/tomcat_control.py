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
    ).isoformat(
        timespec="seconds"
    )


def get_control_config(
    server: dict[str, Any],
) -> dict[str, Any]:
    """
    Return the Tomcat control configuration
    for the supplied server.
    """

    control = server.get(
        "application_control",
        {},
    )

    if not control.get(
        "enabled",
        False,
    ):
        raise ValueError(
            "Application control is disabled "
            f"for {server['name']}"
        )

    required_fields = {
        "tomcat_home",
        "java_home",
        "process_match",
    }

    missing = (
        required_fields
        - control.keys()
    )

    if missing:
        raise ValueError(
            "Missing Tomcat control settings: "
            + ", ".join(
                sorted(missing)
            )
        )

    return control


def build_safe_grep_pattern(
    process_match: str,
) -> str:
    """
    Build a grep pattern that will not match
    the grep process itself.

    Example:

        Dcatalina.base=/imal/TomcatNode2

    becomes:

        [D]catalina.base=/imal/TomcatNode2
    """

    if not process_match:
        raise ValueError(
            "process_match cannot be empty"
        )

    return (
        f"[{process_match[0]}]"
        f"{process_match[1:]}"
    )


def get_tomcat_pids(
    server: dict[str, Any],
) -> list[int]:
    """
    Return the PID(s) belonging to the configured
    Tomcat instance.

    Uses ps + grep instead of pgrep -f because
    pgrep -f can match the lookup command itself.
    """

    control = get_control_config(
        server
    )

    process_match = (
        control["process_match"]
    )

    grep_pattern = (
        build_safe_grep_pattern(
            process_match
        )
    )

    command = (
        "ps -ef | "
        f"grep -- '{grep_pattern}' | "
        "awk '{print $2}'"
    )

    stdout, stderr, exit_code = (
        execute_ssh_command(
            server,
            command,
        )
    )

    pids: list[int] = []

    for line in stdout.splitlines():
        value = line.strip()

        if value.isdigit():
            pids.append(
                int(value)
            )

    logger.debug(
        "CONTROL | %s | "
        "Tomcat PID lookup | PIDs=%s",
        server["id"],
        pids,
    )

    return pids


def wait_for_tomcat_stop(
    server: dict[str, Any],
    timeout: int = 10,
) -> bool:
    """
    Wait until the configured Tomcat process
    is no longer present.
    """

    deadline = (
        time.time()
        + timeout
    )

    while time.time() < deadline:
        pids = get_tomcat_pids(
            server
        )

        if not pids:
            return True

        logger.info(
            "CONTROL | %s | "
            "waiting for Tomcat to stop | "
            "PIDs=%s",
            server["id"],
            pids,
        )

        time.sleep(1)

    return False


def wait_for_tomcat_start(
    server: dict[str, Any],
    timeout: int = 60,
) -> bool:
    """
    Wait until the configured Tomcat process
    appears.
    """

    deadline = (
        time.time()
        + timeout
    )

    while time.time() < deadline:
        pids = get_tomcat_pids(
            server
        )

        if pids:
            return True

        logger.info(
            "CONTROL | %s | "
            "waiting for Tomcat process",
            server["id"],
        )

        time.sleep(2)

    return False


def stop_tomcat(
    server: dict[str, Any],
) -> dict[str, Any]:
    """
    Hard-stop Tomcat using kill -9.

    This mirrors the tested UAT procedure:

        find PID
        kill -9 PID
        verify process is gone
    """

    control = get_control_config(
        server
    )

    kill_timeout = int(
        control.get(
            "kill_timeout",
            10,
        )
    )

    pids_before = get_tomcat_pids(
        server
    )

    if not pids_before:
        logger.info(
            "CONTROL | %s | "
            "Tomcat already stopped",
            server["id"],
        )

        return {
            "stopped": True,
            "already_stopped": True,
            "forced": False,
            "method": "none",
            "pids_before": [],
        }

    logger.warning(
        "CONTROL | %s | "
        "forcing Tomcat shutdown | "
        "PIDs=%s",
        server["id"],
        pids_before,
    )

    killed_pids: list[int] = []
    disappeared_pids: list[int] = []

    for pid in pids_before:
        command = (
            f"if kill -0 {pid} 2>/dev/null; "
            f"then kill -9 {pid}; "
            "else echo "
            f"'PID {pid} already disappeared'; "
            "fi"
        )

        stdout, stderr, exit_code = (
            execute_ssh_command(
                server,
                command,
            )
        )

        output = (
            stderr.strip()
            or stdout.strip()
        )

        if exit_code == 0:
            if (
                "already disappeared"
                in output
            ):
                disappeared_pids.append(
                    pid
                )

                logger.info(
                    "CONTROL | %s | "
                    "PID=%s already disappeared",
                    server["id"],
                    pid,
                )

            else:
                killed_pids.append(
                    pid
                )

                logger.info(
                    "CONTROL | %s | "
                    "kill -9 sent to PID=%s",
                    server["id"],
                    pid,
                )

        else:
            logger.warning(
                "CONTROL | %s | "
                "kill -9 returned exit=%s "
                "for PID=%s | %s",
                server["id"],
                exit_code,
                pid,
                output,
            )

    if not wait_for_tomcat_stop(
        server,
        timeout=kill_timeout,
    ):
        remaining_pids = (
            get_tomcat_pids(
                server
            )
        )

        raise RuntimeError(
            "Tomcat process still running "
            "after kill -9: "
            f"{remaining_pids}"
        )

    logger.info(
        "CONTROL | %s | "
        "Tomcat stopped successfully",
        server["id"],
    )

    return {
        "stopped": True,
        "already_stopped": False,
        "forced": True,
        "method": "kill -9",
        "pids_before": pids_before,
        "killed_pids": killed_pids,
        "disappeared_pids": (
            disappeared_pids
        ),
    }


def start_tomcat(
    server: dict[str, Any],
) -> dict[str, Any]:
    """
    Start Tomcat using startup.sh.

    JAVA_HOME is explicitly exported because
    SSH control sessions are non-interactive
    and may not load the user's shell profile.
    """

    control = get_control_config(
        server
    )

    tomcat_home = (
        control["tomcat_home"]
    )

    java_home = (
        control["java_home"]
    )

    startup_timeout = int(
        control.get(
            "startup_timeout",
            60,
        )
    )

    existing_pids = (
        get_tomcat_pids(
            server
        )
    )

    if existing_pids:
        logger.warning(
            "CONTROL | %s | "
            "Tomcat already running | "
            "PIDs=%s",
            server["id"],
            existing_pids,
        )

        return {
            "started": True,
            "already_running": True,
            "pids": existing_pids,
        }

    logger.warning(
        "CONTROL | %s | "
        "starting Tomcat | "
        "JAVA_HOME=%s | "
        "TOMCAT_HOME=%s",
        server["id"],
        java_home,
        tomcat_home,
    )

    startup_command = (
        f"export JAVA_HOME='{java_home}'; "
        "export PATH=\"$JAVA_HOME/bin:$PATH\"; "
        f"cd '{tomcat_home}/bin' && "
        "./startup.sh"
    )

    stdout, stderr, exit_code = (
        execute_ssh_command(
            server,
            startup_command,
        )
    )

    logger.info(
        "CONTROL | %s | "
        "startup.sh exit=%s | "
        "stdout=%s | stderr=%s",
        server["id"],
        exit_code,
        stdout.strip(),
        stderr.strip(),
    )

    if exit_code != 0:
        raise RuntimeError(
            "startup.sh failed: "
            f"{stderr.strip() or stdout.strip()}"
        )

    if not wait_for_tomcat_start(
        server,
        timeout=startup_timeout,
    ):
        raise RuntimeError(
            "Tomcat did not start within "
            f"{startup_timeout} seconds"
        )

    pids = get_tomcat_pids(
        server
    )

    logger.info(
        "CONTROL | %s | "
        "Tomcat started successfully | "
        "PIDs=%s",
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
    """
    Wait until the configured IMAL API reports
    a healthy response.
    """

    deadline = (
        time.time()
        + timeout
    )

    last_result: (
        dict[str, Any] | None
    ) = None

    logger.info(
        "CONTROL | %s | "
        "waiting for API health",
        server["id"],
    )

    while time.time() < deadline:
        last_result = (
            check_account_api(
                server
            )
        )

        if last_result.get(
            "healthy"
        ):
            logger.info(
                "CONTROL | %s | "
                "API health check successful",
                server["id"],
            )

            return last_result

        logger.info(
            "CONTROL | %s | "
            "API not healthy yet",
            server["id"],
        )

        time.sleep(5)

    if last_result is None:
        raise RuntimeError(
            "API health check did not run"
        )

    logger.warning(
        "CONTROL | %s | "
        "API did not become healthy "
        "within %s seconds",
        server["id"],
        timeout,
    )

    return last_result


def restart_tomcat(
    server: dict[str, Any],
) -> dict[str, Any]:
    """
    Hard restart the configured Tomcat instance.

    Flow:

        1. Find real Tomcat PID(s)
        2. kill -9 PID(s)
        3. Verify Tomcat stopped
        4. Pause briefly
        5. Export JAVA_HOME
        6. Run startup.sh
        7. Verify new Tomcat PID(s)
        8. Verify IMAL API health
    """

    get_control_config(
        server
    )

    started_at = (
        current_timestamp()
    )

    logger.warning(
        "CONTROL | %s | "
        "Tomcat hard restart requested",
        server["id"],
    )

    try:
        stop_result = (
            stop_tomcat(
                server
            )
        )

        #
        # Match the tested UAT sequence.
        #
        time.sleep(2)

        start_result = (
            start_tomcat(
                server
            )
        )

        api_result = (
            wait_for_api_health(
                server,
                timeout=90,
            )
        )

        success = bool(
            api_result.get(
                "healthy"
            )
        )

        logger.info(
            "CONTROL | %s | "
            "restart completed | "
            "api_healthy=%s",
            server["id"],
            success,
        )

        return {
            "success": success,
            "server_id": (
                server["id"]
            ),
            "server_name": (
                server["name"]
            ),
            "message": (
                "Application restarted successfully"
                if success
                else (
                    "Tomcat restarted but API "
                    "health check did not return "
                    "Success"
                )
            ),
            "stop": stop_result,
            "start": start_result,
            "api": {
                "healthy": (
                    api_result.get(
                        "healthy"
                    )
                ),
                "status_desc": (
                    api_result.get(
                        "status_desc"
                    )
                ),
                "http_status": (
                    api_result.get(
                        "http_status"
                    )
                ),
                "response_time_ms": (
                    api_result.get(
                        "response_time_ms"
                    )
                ),
            },
            "started_at": (
                started_at
            ),
            "completed_at": (
                current_timestamp()
            ),
        }

    except Exception as exception:
        logger.exception(
            "CONTROL | %s | "
            "restart failed",
            server["id"],
        )

        return {
            "success": False,
            "server_id": (
                server["id"]
            ),
            "server_name": (
                server["name"]
            ),
            "message": str(
                exception
            ),
            "started_at": (
                started_at
            ),
            "completed_at": (
                current_timestamp()
            ),
        }
