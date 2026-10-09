"""Local-only Temporal development server bundled through the Python SDK."""

import asyncio
from pathlib import Path

from temporalio.testing import WorkflowEnvironment


async def run() -> None:
    Path(".temporal").mkdir(exist_ok=True)
    async with await WorkflowEnvironment.start_local(
        port=7233, ui=True, ui_port=8233,
        dev_server_database_filename=".temporal/temporal.db",
    ):
        print("Temporal development server: localhost:7233 (UI: localhost:8233)", flush=True)
        await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
