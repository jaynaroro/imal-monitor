import logging

import os

import time

from datetime import datetime

from typing import Any

from zoneinfo import ZoneInfo

from app.database_cache import update_database_cache

import pyodbc

import yaml





logger = logging.getLogger(__name__)



NAIROBI_TIMEZONE = ZoneInfo("Africa/Nairobi")



DATABASE_CONFIG_FILE = "config/databases.yml"



DEFAULT_CONNECTION_TIMEOUT = 5





def load_databases() -> list[dict[str, Any]]:

    """

    Load database definitions from config/databases.yml.

    """



    with open(

        DATABASE_CONFIG_FILE,

        "r",

        encoding="utf-8",

    ) as file:

        config = yaml.safe_load(file) or {}



    databases = config.get("databases", [])



    return [

        database

        for database in databases

        if database.get("enabled", True)

    ]





def build_connection_string(

    database: dict[str, Any],

) -> str:

    """

    Build a SQL Server ODBC connection string.



    Credentials are read from environment variables.

    They are never stored in databases.yml.

    """



    username_env = database["username_env"]

    password_env = database["password_env"]



    username = os.getenv(username_env)

    password = os.getenv(password_env)



    if not username:

        raise ValueError(

            f"Environment variable "

            f"'{username_env}' is not set"

        )



    if not password:

        raise ValueError(

            f"Environment variable "

            f"'{password_env}' is not set"

        )



    host = database["host"]

    port = database.get("port", 1433)

    database_name = database["database"]



    return (

        "DRIVER={ODBC Driver 17 for SQL Server};"

        f"SERVER={host},{port};"

        f"DATABASE={database_name};"

        f"UID={username};"

        f"PWD={password};"

        "Encrypt=no;"

        "TrustServerCertificate=yes;"

        f"Connection Timeout={DEFAULT_CONNECTION_TIMEOUT};"

    )





def sanitize_database_error(

    error: Exception,

) -> str:

    """

    Convert database exceptions into safe dashboard messages.



    Avoid returning full ODBC connection/error details to

    the frontend.

    """



    message = str(error).lower()



    if "login failed" in message:

        return "Database authentication failed"



    if (

        "timeout" in message

        or "timed out" in message

    ):

        return "Database connection timed out"



    if (

        "server does not exist" in message

        or "server is unavailable" in message

    ):

        return "Database server is unreachable"



    if "cannot open database" in message:

        return "Target database is unavailable"



    if "environment variable" in message:

        return str(error)



    return "Database connection or query failed"





def check_database(

    database: dict[str, Any],

) -> dict[str, Any]:

    """

    Connect to one SQL Server database and execute SELECT 1.

    """



    database_id = database["id"]

    database_name = database["name"]

    host = database["host"]

    port = database.get("port", 1433)

    target_database = database["database"]



    checked_at = datetime.now(

        NAIROBI_TIMEZONE

    ).isoformat(timespec="seconds")



    started = time.perf_counter()



    connection = None

    cursor = None



    try:

        connection_string = build_connection_string(

            database

        )



        connection = pyodbc.connect(

            connection_string,

            timeout=DEFAULT_CONNECTION_TIMEOUT,

        )



        cursor = connection.cursor()



        cursor.execute("SELECT 1")



        row = cursor.fetchone()



        if row is None or row[0] != 1:

            raise RuntimeError(

                "Database health query returned "

                "an unexpected result"

            )



        response_time_ms = (

            time.perf_counter() - started

        ) * 1000



        logger.info(

            "Database check successful: %s (%s) %.2f ms",

            database_name,

            database_id,

            response_time_ms,

        )



        return {

            "id": database_id,

            "name": database_name,

            "type": database.get(

                "type",

                "sqlserver",

            ),

            "host": host,

            "port": port,

            "database": target_database,

            "status": "healthy",

            "connection": "healthy",

            "query_status": "success",

            "response_time_ms": round(

                response_time_ms,

                2,

            ),

            "checked_at": checked_at,

            "error": None,

        }



    except Exception as error:

        response_time_ms = (

            time.perf_counter() - started

        ) * 1000



        safe_error = sanitize_database_error(

            error

        )



        logger.warning(

            "Database check failed: %s (%s): %s",

            database_name,

            database_id,

            safe_error,

        )



        return {

            "id": database_id,

            "name": database_name,

            "type": database.get(

                "type",

                "sqlserver",

            ),

            "host": host,

            "port": port,

            "database": target_database,

            "status": "unhealthy",

            "connection": "failed",

            "query_status": "failed",

            "response_time_ms": round(

                response_time_ms,

                2,

            ),

            "checked_at": checked_at,

            "error": safe_error,

        }



    finally:

        if cursor is not None:

            try:

                cursor.close()

            except Exception:

                pass



        if connection is not None:

            try:

                connection.close()

            except Exception:

                pass


def check_all_databases() -> list[dict[str, Any]]:

    """

    Run the health check against every enabled database

    and update the database cache.

    """



    databases = load_databases()



    results = []



    for database in databases:

        result = check_database(database)



        update_database_cache(

            database["id"],

            result,

        )



        results.append(result)



    return results



def check_single_database(

    database_id: str,

) -> dict[str, Any]:

    """

    Run a health check against one configured database

    and update its cache entry.

    """



    databases = load_databases()



    database = next(

        (

            item

            for item in databases

            if item["id"] == database_id

        ),

        None,

    )



    if database is None:

        raise ValueError(

            f"Database '{database_id}' was not found"

        )



    result = check_database(database)



    update_database_cache(

        database_id,

        result,

    )



    return result
