from copy import deepcopy

from threading import Lock

from typing import Any, Optional





_database_cache: dict[str, dict[str, Any]] = {}

_cache_lock = Lock()





def initialize_database_cache(

    databases: list[dict[str, Any]],

) -> None:

    """

    Create an initial cache entry for every configured database.

    """



    with _cache_lock:

        _database_cache.clear()



        for database in databases:

            database_id = database["id"]



            _database_cache[database_id] = {

                "id": database_id,

                "name": database["name"],

                "type": database.get(

                    "type",

                    "sqlserver",

                ),

                "host": database["host"],

                "port": database.get(

                    "port",

                    1433,

                ),

                "database": database["database"],

                "status": "unknown",

                "connection": "unknown",

                "query_status": "unknown",

                "response_time_ms": None,

                "checked_at": None,

                "error": None,

            }





def update_database_cache(

    database_id: str,

    result: dict[str, Any],

) -> None:

    """

    Replace the cached result for one database.

    """



    with _cache_lock:

        _database_cache[database_id] = deepcopy(

            result

        )





def get_database_cache() -> list[dict[str, Any]]:

    """

    Return all cached database results.

    """



    with _cache_lock:

        return deepcopy(

            list(_database_cache.values())

        )





def get_single_database_cache(

    database_id: str,

) -> Optional[dict[str, Any]]:

    """

    Return one cached database result.

    """



    with _cache_lock:

        result = _database_cache.get(

            database_id

        )



        if result is None:

            return None



        return deepcopy(result)
