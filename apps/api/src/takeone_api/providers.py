"""Provider seam. Adapters never receive ORM objects or database sessions."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol

@dataclass(frozen=True)
class GenerationSpec:
    description: str
    shot_type: str
    duration_seconds: Decimal
    number_of_characters: int
    dialogue_present: bool
    object_interaction: bool
    motion_complexity: str
    camera_motion: str
    quality_threshold: str

    def snapshot(self) -> dict:
        return {
            "description": self.description,
            "shot_type": self.shot_type,
            "duration_seconds": str(self.duration_seconds),
            "number_of_characters": self.number_of_characters,
            "dialogue_present": self.dialogue_present,
            "object_interaction": self.object_interaction,
            "motion_complexity": self.motion_complexity,
            "camera_motion": self.camera_motion,
            "quality_threshold": self.quality_threshold,
        }

    @classmethod
    def from_snapshot(cls, snapshot: dict) -> "GenerationSpec":
        keys = cls.__dataclass_fields__
        return cls(**{key: Decimal(snapshot[key]) if key == "duration_seconds" else snapshot[key] for key in keys})


@dataclass(frozen=True)
class ProviderCapabilities:
    name: str
    models: tuple[str, ...]
    max_duration_seconds: Decimal
    media_type: str
    is_mock: bool = False


@dataclass(frozen=True)
class ProviderJobStatus:
    state: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    output_url: str | None = None
    media_type: str | None = None
    actual_cost: Decimal | None = None
    error_message: str | None = None


class VideoProvider(Protocol):
    def capabilities(self) -> ProviderCapabilities: ...
    def estimate_cost(self, spec: GenerationSpec, model: str) -> Decimal: ...
    def generate(self, spec: GenerationSpec, prompt: str, model: str, idempotency_key: str) -> str: ...
    def get_status(self, job_id: str) -> ProviderJobStatus: ...
    def cancel(self, job_id: str) -> bool: ...


class MockVideoProvider:
    """Stateless deterministic adapter for local economics and workflow testing."""

    def __init__(
        self, name: str = "mock", model: str = "mock-v1",
        base_cost: Decimal = Decimal("0.10"),
        per_second_cost: Decimal = Decimal("0.04"),
    ):
        self.name = name
        self.model = model
        self.base_cost = base_cost
        self.per_second_cost = per_second_cost

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name=self.name, models=(self.model,), max_duration_seconds=Decimal("15"),
            media_type="image/svg+xml", is_mock=True,
        )

    def estimate_cost(self, spec: GenerationSpec, model: str) -> Decimal:
        self._validate(spec, model)
        motion = Decimal("0.08") if spec.motion_complexity == "high" else Decimal("0.00")
        quality = Decimal("0.05") if spec.quality_threshold == "high" else Decimal("0.00")
        return (self.base_cost + spec.duration_seconds * self.per_second_cost + motion + quality).quantize(Decimal("0.0001"))

    def generate(self, spec: GenerationSpec, prompt: str, model: str, idempotency_key: str) -> str:
        self._validate(spec, model)
        if not prompt.strip():
            raise ValueError("Prompt is required")
        return f"{self.name}:{idempotency_key}"

    def get_status(self, job_id: str) -> ProviderJobStatus:
        if not job_id.startswith(f"{self.name}:"):
            raise ValueError("Unknown mock job")
        return ProviderJobStatus(state="succeeded", output_url="/mock-frame.svg", media_type="image/svg+xml")

    def cancel(self, job_id: str) -> bool:
        if not job_id.startswith(f"{self.name}:"):
            raise ValueError("Unknown mock job")
        return True

    def _validate(self, spec: GenerationSpec, model: str) -> None:
        if model not in self.capabilities().models:
            raise ValueError("Unsupported model")
        if spec.duration_seconds <= 0 or spec.duration_seconds > self.capabilities().max_duration_seconds:
            raise ValueError("Shot duration is outside provider limits")


class ProviderRegistry:
    def __init__(self, providers: list[VideoProvider]):
        self._providers = {provider.capabilities().name: provider for provider in providers}

    def get(self, name: str) -> VideoProvider:
        try:
            return self._providers[name]
        except KeyError as exc:
            raise ValueError(f"Unknown provider: {name}") from exc

    def capabilities(self) -> list[ProviderCapabilities]:
        return [provider.capabilities() for provider in self._providers.values()]


providers = ProviderRegistry([
    MockVideoProvider(),
    MockVideoProvider("mock-alt", "mock-alt-v1", Decimal("0.06"), Decimal("0.06")),
])
