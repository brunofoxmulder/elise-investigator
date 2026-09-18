"""RC14: native Assist origin with the existing RC13 reader and proof lifecycle."""

from aiohttp import web

import main_v2_rc13 as rc13

VERSION = "0.3.0-rc.14"


async def create_app() -> web.Application:
    return await rc13.create_app(version=VERSION)


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
