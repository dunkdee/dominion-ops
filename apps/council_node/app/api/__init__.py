"""HTTP surface. Each module owns one concern and exports `router`."""

from . import agents, founder, governance, health, lanes, models, receipts, tasks

ROUTERS = (
    health.router, tasks.router, lanes.router, receipts.router,
    governance.router, agents.router, models.router, founder.router,
)

__all__ = ["ROUTERS"]
