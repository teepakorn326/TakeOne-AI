import asyncio
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from .config import settings
from .db import SessionLocal
from .generation import GenerationActivities
from .providers import providers
from .workflow import GenerateShotWorkflow


async def run_worker() -> None:
    client = await Client.connect(settings.temporal_address)
    activities = GenerationActivities(SessionLocal, providers)
    with ThreadPoolExecutor(max_workers=8) as executor:
        worker = Worker(
            client, task_queue=settings.temporal_task_queue,
            workflows=[GenerateShotWorkflow],
            activities=[activities.submit, activities.poll, activities.cancel, activities.fail],
            activity_executor=executor,
        )
        await worker.run()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()

