"""Council Node service entrypoint.

Binds to loopback by default (work order §7). Public exposure is Caddy's job,
and only for the endpoints the Caddyfile forwards.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api import ROUTERS
from .config import settings
from .logging import configure_logging, get_logger

cfg = settings()
configure_logging(secret_values=cfg.secret_values())
log = get_logger("main")

@asynccontextmanager
async def lifespan(_: FastAPI):
    log.info("council node starting: %s", cfg.redacted())
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Dominion Council Node",
    description="Governed orchestration under RADAH MEMSHALAH",
    version="0.1.0",
    docs_url=None,   # no interactive docs on a governed control plane
    redoc_url=None,
)

for router in ROUTERS:
    app.include_router(router)


def main() -> None:
    import uvicorn

    uvicorn.run(
        "apps.council_node.app.main:app",
        host=cfg.bind_host, port=cfg.bind_port, log_config=None,
    )


if __name__ == "__main__":
    main()
