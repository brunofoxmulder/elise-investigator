from __future__ import annotations

from aiohttp import web

import main_dev68 as impl

VERSION = "0.2.0-dev.69"


async def create_app() -> web.Application:
    # dev.69 deliberately reuses the dev.68 causal logic unchanged.
    # The difference is qualification: the dev.67 terrain cases are now
    # frozen as explicit regression tests before any HAOS promotion.
    impl.VERSION = VERSION
    return await impl.create_app()


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8099, access_log=None)
