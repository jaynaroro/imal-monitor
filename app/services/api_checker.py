import copy
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.config import (
    IMAL_PASSWORD,
    IMAL_REQUEST_TIMEOUT,
    IMAL_VERIFY_SSL,
    load_account_request_template,
)


NAIROBI_TIMEZONE = ZoneInfo("Africa/Nairobi")


def current_timestamp() -> str:
    return datetime.now(
        NAIROBI_TIMEZONE
    ).isoformat(timespec="seconds")


def find_status_desc(value: Any) -> str | None:
    """
    Recursively search a JSON response for statusDesc.

    The response nesting may differ depending on the IMAL gateway.
    """

    if isinstance(value, dict):
        for key, child in value.items():
            normalized_key = str(key).replace(
                "_",
                "",
            ).lower()

            if normalized_key == "statusdesc":
                if child is None:
                    return None

                return str(child)

            result = find_status_desc(child)

            if result is not None:
                return result

    elif isinstance(value, list):
        for child in value:
            result = find_status_desc(child)

            if result is not None:
                return result

    return None


def build_account_request() -> dict[str, Any]:
    request_template = load_account_request_template()
    payload = copy.deepcopy(request_template)

    requester_context = payload["requesterContext"]

    requester_context["password"] = IMAL_PASSWORD
    requester_context["requesterTimeStamp"] = current_timestamp()

    return payload


def check_account_api(
    server: dict[str, Any],
) -> dict[str, Any]:
    start_time = time.perf_counter()
    checked_at = current_timestamp()

    try:
        payload = build_account_request()

        response = httpx.post(
            server["api_url"],
            json=payload,
            timeout=IMAL_REQUEST_TIMEOUT,
            verify=IMAL_VERIFY_SSL,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        response_time_ms = round(
            (time.perf_counter() - start_time) * 1000,
            2,
        )

        try:
            response_data = response.json()
        except ValueError:
            return {
                "status": "unhealthy",
                "healthy": False,
                "status_desc": None,
                "http_status": response.status_code,
                "response_time_ms": response_time_ms,
                "error": (
                    "Server returned a response that was not valid JSON"
                ),
                "checked_at": checked_at,
            }

        status_desc = find_status_desc(response_data)

        is_healthy = (
            response.is_success
            and status_desc is not None
            and status_desc.strip().lower() == "success"
        )

        return {
            "status": (
                "healthy"
                if is_healthy
                else "unhealthy"
            ),
            "healthy": is_healthy,
            "status_desc": status_desc,
            "http_status": response.status_code,
            "response_time_ms": response_time_ms,
            "error": (
                None
                if is_healthy
                else "IMAL did not return statusDesc: Success"
            ),
            "checked_at": checked_at,
        }

    except httpx.TimeoutException:
        response_time_ms = round(
            (time.perf_counter() - start_time) * 1000,
            2,
        )

        return {
            "status": "unhealthy",
            "healthy": False,
            "status_desc": None,
            "http_status": None,
            "response_time_ms": response_time_ms,
            "error": (
                f"Request timed out after "
                f"{IMAL_REQUEST_TIMEOUT} seconds"
            ),
            "checked_at": checked_at,
        }

    except httpx.ConnectError as exception:
        response_time_ms = round(
            (time.perf_counter() - start_time) * 1000,
            2,
        )

        return {
            "status": "unhealthy",
            "healthy": False,
            "status_desc": None,
            "http_status": None,
            "response_time_ms": response_time_ms,
            "error": f"Connection failed: {exception}",
            "checked_at": checked_at,
        }

    except httpx.HTTPError as exception:
        response_time_ms = round(
            (time.perf_counter() - start_time) * 1000,
            2,
        )

        return {
            "status": "unhealthy",
            "healthy": False,
            "status_desc": None,
            "http_status": None,
            "response_time_ms": response_time_ms,
            "error": f"HTTP error: {exception}",
            "checked_at": checked_at,
        }

    except Exception as exception:
        response_time_ms = round(
            (time.perf_counter() - start_time) * 1000,
            2,
        )

        return {
            "status": "unhealthy",
            "healthy": False,
            "status_desc": None,
            "http_status": None,
            "response_time_ms": response_time_ms,
            "error": f"Unexpected error: {exception}",
            "checked_at": checked_at,
        }
