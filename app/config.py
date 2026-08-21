import json
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"

SERVERS_FILE = CONFIG_DIR / "servers.yml"
ACCOUNT_REQUEST_FILE = CONFIG_DIR / "account_request.json"

load_dotenv(BASE_DIR / ".env")


def get_boolean_environment_variable(
    name: str,
    default: bool = False,
) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


IMAL_PASSWORD = os.getenv("IMAL_PASSWORD", "")
IMAL_REQUEST_TIMEOUT = float(
    os.getenv("IMAL_REQUEST_TIMEOUT", "15")
)
IMAL_VERIFY_SSL = get_boolean_environment_variable(
    "IMAL_VERIFY_SSL",
    default=False,
)

SSH_PRIVATE_KEY = os.getenv(
    "SSH_PRIVATE_KEY",
    "/run/secrets/monitoring_ed25519",
)

SSH_KNOWN_HOSTS = os.getenv(
    "SSH_KNOWN_HOSTS",
    "/run/secrets/known_hosts",
)

SSH_CONNECT_TIMEOUT = float(
    os.getenv("SSH_CONNECT_TIMEOUT", "10")
)

SSH_COMMAND_TIMEOUT = float(
    os.getenv("SSH_COMMAND_TIMEOUT", "20")
)

AUTO_REFRESH_ENABLED = get_boolean_environment_variable(
    "AUTO_REFRESH_ENABLED",
    default=True,
)

AUTO_REFRESH_MINUTES = int(
    os.getenv(
        "AUTO_REFRESH_MINUTES",
        "15",
    )
)

if AUTO_REFRESH_MINUTES < 1:
    raise ValueError(
        "AUTO_REFRESH_MINUTES must be at least 1"
    )

def load_servers() -> list[dict[str, Any]]:
    if not SERVERS_FILE.exists():
        raise FileNotFoundError(
            f"Server configuration file not found: "
            f"{SERVERS_FILE}"
        )

    with SERVERS_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = yaml.safe_load(file)

    servers = data.get("servers", [])

    if not servers:
        raise ValueError(
            "No servers were defined in "
            "config/servers.yml"
        )

    required_fields = {
        "id",
        "name",
        "api_url_env",
        "ssh_host_env",
        "ssh_username_env",
        "ssh_port",
    }

    for server in servers:
        missing_fields = (
            required_fields - server.keys()
        )

        if missing_fields:
            raise ValueError(
                "Server configuration is missing "
                f"fields: "
                f"{', '.join(sorted(missing_fields))}"
            )

        api_url_env = server["api_url_env"]
        ssh_host_env = server["ssh_host_env"]
        ssh_username_env = (
            server["ssh_username_env"]
        )

        api_url = os.getenv(api_url_env)
        ssh_host = os.getenv(ssh_host_env)
        ssh_username = os.getenv(
            ssh_username_env
        )

        missing_environment_variables = []

        if not api_url:
            missing_environment_variables.append(
                api_url_env
            )

        if not ssh_host:
            missing_environment_variables.append(
                ssh_host_env
            )

        if not ssh_username:
            missing_environment_variables.append(
                ssh_username_env
            )

        if missing_environment_variables:
            raise ValueError(
                "Missing required environment "
                "variables for server "
                f"'{server['id']}': "
                + ", ".join(
                    missing_environment_variables
                )
            )

        # Resolve environment-variable references
        # into the fields used by the rest of the
        # application.
        server["api_url"] = api_url
        server["ssh_host"] = ssh_host
        server["ssh_username"] = ssh_username

    return servers


def load_account_request_template() -> dict[str, Any]:
    if not ACCOUNT_REQUEST_FILE.exists():
        raise FileNotFoundError(
            f"Account request template not found: "
            f"{ACCOUNT_REQUEST_FILE}"
        )

    with ACCOUNT_REQUEST_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)
