import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import paramiko

from app.config import (
    SSH_COMMAND_TIMEOUT,
    SSH_CONNECT_TIMEOUT,
    SSH_KNOWN_HOSTS,
    SSH_PRIVATE_KEY,
)

from app.services.system_metrics import (
    calculate_cpu_percent,
    calculate_overall_status,
    extract_section,
    parse_filesystems,
    parse_load_average,
    parse_memory,
    parse_uptime,
)


NAIROBI_TIMEZONE = ZoneInfo("Africa/Nairobi")


SYSTEM_METRICS_COMMAND = r"""
LC_ALL=C bash -c '
echo "===DF===";
df -P -x tmpfs -x devtmpfs -x overlay -x squashfs 2>/dev/null;

echo "===MEM===";
free -b;

echo "===CPU1===";
head -n 1 /proc/stat;
sleep 1;

echo "===CPU2===";
head -n 1 /proc/stat;

echo "===LOAD===";
cat /proc/loadavg;

echo "===UPTIME===";
cat /proc/uptime;
'
"""


def current_timestamp() -> str:
    return datetime.now(
        NAIROBI_TIMEZONE
    ).isoformat(timespec="seconds")


def create_ssh_client() -> paramiko.SSHClient:
    client = paramiko.SSHClient()

    known_hosts_path = Path(SSH_KNOWN_HOSTS)

    if known_hosts_path.exists():
        client.load_host_keys(str(known_hosts_path))
        client.set_missing_host_key_policy(
            paramiko.RejectPolicy()
        )
    else:
        # Useful during local development.
        # For production, mount a proper known_hosts file.
        client.set_missing_host_key_policy(
            paramiko.AutoAddPolicy()
        )

    return client


def execute_ssh_command(
    server: dict[str, Any],
    command: str,
) -> tuple[str, str, int]:
    private_key_path = Path(SSH_PRIVATE_KEY)

    if not private_key_path.exists():
        raise FileNotFoundError(
            f"SSH private key not found: {private_key_path}"
        )

    client = create_ssh_client()

    try:
        client.connect(
            hostname=server["ssh_host"],
            port=int(server.get("ssh_port", 22)),
            username=server["ssh_username"],
            key_filename=str(private_key_path),
            timeout=SSH_CONNECT_TIMEOUT,
            banner_timeout=SSH_CONNECT_TIMEOUT,
            auth_timeout=SSH_CONNECT_TIMEOUT,
            look_for_keys=False,
            allow_agent=False,
        )

        stdin, stdout, stderr = client.exec_command(
            command,
            timeout=SSH_COMMAND_TIMEOUT,
        )

        exit_code = stdout.channel.recv_exit_status()

        stdout_text = stdout.read().decode(
            "utf-8",
            errors="replace",
        )

        stderr_text = stderr.read().decode(
            "utf-8",
            errors="replace",
        )

        return stdout_text, stderr_text, exit_code

    finally:
        client.close()


def check_ssh_connectivity(
    server: dict[str, Any],
) -> dict[str, Any]:
    started_at = time.perf_counter()
    checked_at = current_timestamp()

    try:
        stdout, stderr, exit_code = execute_ssh_command(
            server,
            "printf 'SSH_OK'",
        )

        response_time_ms = round(
            (time.perf_counter() - started_at) * 1000,
            2,
        )

        healthy = (
            exit_code == 0
            and stdout.strip() == "SSH_OK"
        )

        return {
            "status": "healthy" if healthy else "unhealthy",
            "healthy": healthy,
            "response_time_ms": response_time_ms,
            "error": (
                None
                if healthy
                else stderr.strip() or "SSH command failed"
            ),
            "checked_at": checked_at,
        }

    except Exception as exception:
        return {
            "status": "unhealthy",
            "healthy": False,
            "response_time_ms": round(
                (time.perf_counter() - started_at) * 1000,
                2,
            ),
            "error": str(exception),
            "checked_at": checked_at,
        }

def collect_system_metrics(
    server: dict[str, Any],
) -> dict[str, Any]:
    started_at = time.perf_counter()
    checked_at = current_timestamp()

    try:
        stdout, stderr, exit_code = execute_ssh_command(
            server,
            SYSTEM_METRICS_COMMAND,
        )

        response_time_ms = round(
            (time.perf_counter() - started_at) * 1000,
            2,
        )

        if exit_code != 0:
            return {
                "status": "unhealthy",
                "healthy": False,
                "ssh_status": "unhealthy",
                "cpu": None,
                "memory": None,
                "filesystems": [],
                "load_average": None,
                "uptime": None,
                "response_time_ms": response_time_ms,
                "error": stderr.strip() or (
                    f"Remote command exited with code "
                    f"{exit_code}"
                ),
                "checked_at": checked_at,
            }

        df_output = extract_section(
            stdout,
            "DF",
            "MEM",
        )

        memory_output = extract_section(
            stdout,
            "MEM",
            "CPU1",
        )

        cpu1_output = extract_section(
            stdout,
            "CPU1",
            "CPU2",
        )

        cpu2_output = extract_section(
            stdout,
            "CPU2",
            "LOAD",
        )

        load_output = extract_section(
            stdout,
            "LOAD",
            "UPTIME",
        )

        uptime_output = extract_section(
            stdout,
            "UPTIME",
        )

        cpu_percent = calculate_cpu_percent(
            cpu1_output.strip(),
            cpu2_output.strip(),
        )

        memory = parse_memory(memory_output)
        filesystems = parse_filesystems(df_output)
        load_average = parse_load_average(load_output)
        uptime = parse_uptime(uptime_output)

        overall_status = calculate_overall_status(
            cpu_percent=cpu_percent,
            memory_percent=memory["percent"],
            filesystems=filesystems,
        )

        highest_filesystem = max(
            filesystems,
            key=lambda item: item["usage_percent"],
            default=None,
        )

        return {
            "status": overall_status,
            "healthy": overall_status == "healthy",
            "ssh_status": "healthy",
            "cpu": {
                "percent": cpu_percent,
            },
            "memory": memory,
            "filesystems": filesystems,
            "highest_filesystem": highest_filesystem,
            "load_average": load_average,
            "uptime": uptime,
            "response_time_ms": response_time_ms,
            "error": None,
            "checked_at": checked_at,
        }

    except Exception as exception:
        return {
            "status": "unhealthy",
            "healthy": False,
            "ssh_status": "unhealthy",
            "cpu": None,
            "memory": None,
            "filesystems": [],
            "highest_filesystem": None,
            "load_average": None,
            "uptime": None,
            "response_time_ms": round(
                (time.perf_counter() - started_at) * 1000,
                2,
            ),
            "error": str(exception),
            "checked_at": checked_at,
        }