"""Server entrypoint.

uvicorn 0.36+ chooses its event loop with a `loop_factory` handed to
asyncio.run, which bypasses the event loop policy completely. On Windows that
factory builds a ProactorEventLoop, and psycopg 3 refuses to run async against
one — the server starts, but every query fails.

So the policy is set here, before uvicorn is configured, and uvicorn is asked
for no factory of its own (`loop="none"`) so it falls back to that policy.
Use this instead of calling `uvicorn app.main:app` directly.
"""

import argparse

from app.core.platform import configure_event_loop_policy

configure_event_loop_policy()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the DBPilot API server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        # Supply no loop factory, so the policy set above decides.
        loop="none",
    )


if __name__ == "__main__":
    main()
