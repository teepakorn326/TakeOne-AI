"""Deterministic orchestration only; provider and database work runs in Activities."""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy


ACTIVITY_TIMEOUT = timedelta(seconds=30)
ACTIVITY_RETRY = RetryPolicy(maximum_attempts=3)


@workflow.defn
class GenerateShotWorkflow:
    def __init__(self) -> None:
        self.cancel_requested = False

    @workflow.signal
    def request_cancel(self) -> None:
        self.cancel_requested = True

    @workflow.run
    async def run(self, attempt_id: str, max_polls: int = 120) -> str:
        try:
            await workflow.execute_activity(
                "generation_submit", attempt_id, start_to_close_timeout=ACTIVITY_TIMEOUT,
                retry_policy=ACTIVITY_RETRY,
            )
            for _ in range(max_polls):
                if self.cancel_requested:
                    await workflow.execute_activity(
                        "generation_cancel", attempt_id, start_to_close_timeout=ACTIVITY_TIMEOUT,
                        retry_policy=ACTIVITY_RETRY,
                    )
                    return "cancelled"
                state = await workflow.execute_activity(
                    "generation_poll", attempt_id, start_to_close_timeout=ACTIVITY_TIMEOUT,
                    retry_policy=ACTIVITY_RETRY,
                )
                if state != "pending":
                    return state
                await workflow.sleep(2)
            await workflow.execute_activity(
                "generation_fail", args=[attempt_id, "Provider polling timed out"],
                start_to_close_timeout=ACTIVITY_TIMEOUT, retry_policy=ACTIVITY_RETRY,
            )
            return "failed"
        except Exception:
            await workflow.execute_activity(
                "generation_fail", args=[attempt_id, "Generation workflow failed"],
                start_to_close_timeout=ACTIVITY_TIMEOUT, retry_policy=ACTIVITY_RETRY,
            )
            raise
