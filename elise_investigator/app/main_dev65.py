from __future__ import annotations

from aiohttp import web

import main_dev64 as impl

VERSION = "0.2.0-dev.65"


async def create_app() -> web.Application:
    impl.VERSION = VERSION
    return await impl.create_app()


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
