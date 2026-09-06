"""Platform-specific startup adjustments."""

import asyncio
import sys


def configure_event_loop_policy() -> None:
    """Select an event loop psycopg 3 can drive.

    Windows defaults to ProactorEventLoop, which psycopg 3 refuses to run
    against in async mode. Switching to the selector policy is the documented
    fix. A no-op on every other platform, so CI on Linux is unaffected.
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
