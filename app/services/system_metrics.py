from typing import Any


def extract_section(
    output: str,
    section_name: str,
    next_section_name: str | None = None,
) -> str:
    start_marker = f"==={section_name}==="

    if start_marker not in output:
        return ""

    section = output.split(start_marker, 1)[1]

    if next_section_name:
        next_marker = f"==={next_section_name}==="

        if next_marker in section:
            section = section.split(next_marker, 1)[0]

    return section.strip()


def parse_cpu_line(line: str) -> dict[str, int]:
    parts = line.split()

    if not parts or parts[0] != "cpu":
        raise ValueError(
            f"Invalid /proc/stat CPU line: {line}"
        )

    values = [int(value) for value in parts[1:]]

    while len(values) < 8:
        values.append(0)

    return {
        "user": values[0],
        "nice": values[1],
        "system": values[2],
        "idle": values[3],
        "iowait": values[4],
        "irq": values[5],
        "softirq": values[6],
        "steal": values[7],
    }


def calculate_cpu_percent(
    first_line: str,
    second_line: str,
) -> float:
    first = parse_cpu_line(first_line)
    second = parse_cpu_line(second_line)

    first_idle = first["idle"] + first["iowait"]
    second_idle = second["idle"] + second["iowait"]

    first_total = sum(first.values())
    second_total = sum(second.values())

    total_delta = second_total - first_total
    idle_delta = second_idle - first_idle

    if total_delta <= 0:
        return 0.0

    cpu_percent = (
        (total_delta - idle_delta)
        / total_delta
        * 100
    )

    return round(cpu_percent, 2)


def parse_memory(output: str) -> dict[str, Any]:
    lines = output.splitlines()

    memory_line = next(
        (
            line
            for line in lines
            if line.strip().startswith("Mem:")
        ),
        None,
    )

    if memory_line is None:
        raise ValueError(
            "Could not find memory values in free output"
        )

    parts = memory_line.split()

    if len(parts) < 7:
        raise ValueError(
            f"Unexpected memory output: {memory_line}"
        )

    total_bytes = int(parts[1])
    available_bytes = int(parts[6])

    used_bytes = total_bytes - available_bytes

    memory_percent = (
        used_bytes / total_bytes * 100
        if total_bytes
        else 0
    )

    return {
        "total_bytes": total_bytes,
        "used_bytes": used_bytes,
        "available_bytes": available_bytes,
        "percent": round(memory_percent, 2),
    }


def parse_filesystems(output: str) -> list[dict[str, Any]]:
    lines = output.splitlines()

    filesystems: list[dict[str, Any]] = []

    for line in lines[1:]:
        parts = line.split()

        if len(parts) < 6:
            continue

        filesystem = parts[0]
        total_blocks = int(parts[1])
        used_blocks = int(parts[2])
        available_blocks = int(parts[3])
        percent_text = parts[4]
        mount_point = parts[5]

        usage_percent = int(
            percent_text.rstrip("%")
        )

        filesystems.append(
            {
                "filesystem": filesystem,
                "mount_point": mount_point,
                "total_bytes": total_blocks * 1024,
                "used_bytes": used_blocks * 1024,
                "available_bytes": available_blocks * 1024,
                "usage_percent": usage_percent,
                "status": storage_status(
                    usage_percent
                ),
            }
        )

    return filesystems


def parse_load_average(output: str) -> dict[str, float]:
    parts = output.split()

    if len(parts) < 3:
        raise ValueError(
            f"Invalid load average output: {output}"
        )

    return {
        "load_1": float(parts[0]),
        "load_5": float(parts[1]),
        "load_15": float(parts[2]),
    }


def parse_uptime(output: str) -> dict[str, float]:
    parts = output.split()

    if not parts:
        raise ValueError(
            f"Invalid uptime output: {output}"
        )

    uptime_seconds = float(parts[0])

    return {
        "seconds": round(uptime_seconds, 2),
        "days": round(
            uptime_seconds / 86400,
            2,
        ),
    }


def storage_status(
    usage_percent: float,
) -> str:
    if usage_percent >= 90:
        return "critical"

    if usage_percent >= 80:
        return "warning"

    return "healthy"


def cpu_status(
    cpu_percent: float,
) -> str:
    if cpu_percent >= 90:
        return "critical"

    if cpu_percent >= 75:
        return "warning"

    return "healthy"


def memory_status(
    memory_percent: float,
) -> str:
    if memory_percent >= 90:
        return "critical"

    if memory_percent >= 80:
        return "warning"

    return "healthy"


def calculate_overall_status(
    cpu_percent: float,
    memory_percent: float,
    filesystems: list[dict[str, Any]],
) -> str:
    statuses = [
        cpu_status(cpu_percent),
        memory_status(memory_percent),
    ]

    statuses.extend(
        filesystem["status"]
        for filesystem in filesystems
    )

    if "critical" in statuses:
        return "critical"

    if "warning" in statuses:
        return "warning"

    return "healthy"