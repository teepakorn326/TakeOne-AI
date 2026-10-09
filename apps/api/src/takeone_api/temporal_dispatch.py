from uuid import UUID

from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

from .config import settings
from .workflow import GenerateShotWorkflow


def workflow_id(attempt_id: UUID) -> str:
    return f"takeone-generation-{attempt_id}"


class TemporalDispatcher:
    async def start(self, attempt_id: UUID) -> None:
        client = await Client.connect(settings.temporal_address)
        try:
            await client.start_workflow(
                GenerateShotWorkflow.run, str(attempt_id), id=workflow_id(attempt_id),
                task_queue=settings.temporal_task_queue,
                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
            )
        except WorkflowAlreadyStartedError:
            # A retry with the same HTTP idempotency key must not start a second job.
            pass

    async def cancel(self, attempt_id: UUID) -> None:
        client = await Client.connect(settings.temporal_address)
        handle = client.get_workflow_handle(workflow_id(attempt_id))
        await handle.signal(GenerateShotWorkflow.request_cancel)


def get_dispatcher() -> TemporalDispatcher:
    return TemporalDispatcher()

