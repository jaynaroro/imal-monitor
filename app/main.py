import logging

from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.cache import (
    get_cache,
    get_server_cache,
    initialize_cache,
)

from app.config import (
    AUTO_REFRESH_ENABLED,
    load_servers,
)

from app.jobs.scheduler import (
    get_scheduler_status,
    start_scheduler,
    stop_scheduler,
)

from app.services.monitor import (
    check_all_server_apis,
    check_all_server_systems,
    check_all_servers,
    check_single_server_all,
    check_single_server_api,
    check_single_server_system,
)

from app.services.tomcat_control import (
    restart_tomcat,
)


logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | %(levelname)s | "
        "%(name)s | %(message)s"
    ),
)

logger = logging.getLogger(__name__)


NAIROBI_TIMEZONE = ZoneInfo(
    "Africa/Nairobi"
)


servers = load_servers()

initialize_cache(
    servers
)


def find_server(
    server_id: str,
) -> dict:
    """
    Find a configured server using its ID.

    Raises HTTP 404 if the server does not exist.
    """

    server = next(
        (
            item
            for item in servers
            if item["id"] == server_id
        ),
        None,
    )

    if server is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Server '{server_id}' "
                "was not found"
            ),
        )

    return server


@asynccontextmanager
async def lifespan(
    app: FastAPI,
):
    """
    Run an initial monitoring check and manage
    the automatic background scheduler.
    """

    logger.info(
        "IMAL Infrastructure Monitor starting"
    )

    try:
        check_all_servers(
            servers
        )

    except Exception:
        logger.exception(
            "Initial monitoring check failed"
        )

    if AUTO_REFRESH_ENABLED:
        try:
            start_scheduler(
                servers
            )

        except Exception:
            logger.exception(
                "Could not start monitoring scheduler"
            )

    else:
        logger.warning(
            "Automatic monitoring checks are disabled"
        )

    yield

    try:
        stop_scheduler()

    except Exception:
        logger.exception(
            "Could not stop monitoring scheduler cleanly"
        )

    logger.info(
        "IMAL Infrastructure Monitor stopped"
    )


app = FastAPI(
    title="IMAL Infrastructure Monitor",
    version="1.2.0",
    lifespan=lifespan,
)


app.mount(
    "/static",
    StaticFiles(
        directory="app/static"
    ),
    name="static",
)


templates = Jinja2Templates(
    directory="app/templates",
)


@app.get("/health")
def health_check() -> dict:
    """
    Health endpoint for Docker and external monitoring.
    """

    return {
        "status": "healthy",
        "application": (
            "IMAL Infrastructure Monitor"
        ),
        "timestamp": datetime.now(
            NAIROBI_TIMEZONE
        ).isoformat(
            timespec="seconds"
        ),
        "scheduler": (
            get_scheduler_status()
        ),
    }


@app.get(
    "/",
    response_class=HTMLResponse,
)
def dashboard(
    request: Request,
):
    """
    Render the monitoring dashboard using
    the current cached values.
    """

    controllable_server_ids = {
        server["id"]
        for server in servers
        if server.get(
            "application_control",
            {},
        ).get(
            "enabled",
            False,
        )
    }

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "title": (
                "IMAL Infrastructure Monitor"
            ),
            "servers": get_cache(),
            "scheduler": (
                get_scheduler_status()
            ),
            "controllable_server_ids": (
                controllable_server_ids
            ),
        },
    )


@app.get("/api/status")
def get_all_statuses() -> dict:
    """
    Return the latest cached API and system
    status for all servers.
    """

    return {
        "servers": get_cache(),
        "scheduler": (
            get_scheduler_status()
        ),
        "retrieved_at": datetime.now(
            NAIROBI_TIMEZONE
        ).isoformat(
            timespec="seconds"
        ),
    }


@app.get(
    "/api/status/{server_id}"
)
def get_single_server_status(
    server_id: str,
) -> dict:
    """
    Return the latest cached status
    for one server.
    """

    cached_server = (
        get_server_cache(
            server_id
        )
    )

    if cached_server is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Server '{server_id}' "
                "was not found"
            ),
        )

    return cached_server


@app.post("/api/check")
def run_all_checks() -> dict:
    """
    Run API and system checks against
    all configured servers.
    """

    results = check_all_servers(
        servers
    )

    return {
        "message": (
            "All API and system "
            "checks completed"
        ),
        "results": results,
        "scheduler": (
            get_scheduler_status()
        ),
    }


@app.post("/api/check/api")
def run_all_api_checks() -> dict:
    """
    Run only IMAL API checks for all servers.
    """

    results = (
        check_all_server_apis(
            servers
        )
    )

    return {
        "message": (
            "All API checks completed"
        ),
        "results": results,
    }


@app.post("/api/check/system")
def run_all_system_checks() -> dict:
    """
    Run only SSH resource checks for all servers.
    """

    results = (
        check_all_server_systems(
            servers
        )
    )

    return {
        "message": (
            "All system checks completed"
        ),
        "results": results,
    }


@app.post(
    "/api/check/{server_id}"
)
def run_single_server_checks(
    server_id: str,
) -> dict:
    """
    Run API and system checks for one server.
    """

    server = find_server(
        server_id
    )

    return check_single_server_all(
        server
    )


@app.post(
    "/api/check/{server_id}/api"
)
def run_single_server_api_check(
    server_id: str,
) -> dict:
    """
    Run only the IMAL API check
    for one server.
    """

    server = find_server(
        server_id
    )

    return check_single_server_api(
        server
    )


@app.post(
    "/api/check/{server_id}/system"
)
def run_single_server_system_check(
    server_id: str,
) -> dict:
    """
    Run only the SSH resource check
    for one server.
    """

    server = find_server(
        server_id
    )

    return check_single_server_system(
        server
    )


@app.post(
    "/api/control/{server_id}/restart"
)
def restart_server_application(
    server_id: str,
) -> dict:
    """
    Restart a configured Tomcat instance.

    Application control must explicitly be
    enabled for the server.

    Restart is additionally restricted to
    Node1 and Node2.
    """

    server = find_server(
        server_id
    )

    control = server.get(
        "application_control",
        {},
    )

    if not control.get(
        "enabled",
        False,
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Application control is not "
                "enabled for this server"
            ),
        )

    if server_id not in {
        "node1",
        "node2",
    }:
        raise HTTPException(
            status_code=403,
            detail=(
                "Application restart is only "
                "allowed for Node1 and Node2"
            ),
        )

    logger.warning(
        "CONTROL | %s | "
        "Tomcat restart requested",
        server_id,
    )

    result = restart_tomcat(
        server
    )

    if not result.get(
        "success",
        False,
    ):
        raise HTTPException(
            status_code=500,
            detail=result,
        )

    return result