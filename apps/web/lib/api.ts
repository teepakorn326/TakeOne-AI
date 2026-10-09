export type Session = { workspaceId: string; userId: string; workspaceName: string };
export type Series = { id: string; title: string; description: string; genre: string; status: string };
export type Episode = { id: string; series_id: string; episode_number: number; title: string; status: string };
export type Scene = { id: string; episode_id: string; scene_number: number; description: string; location: string; time_of_day: string };
export type Shot = { id: string; scene_id: string; shot_number: number; description: string; shot_type: string; duration_seconds: string; number_of_characters: number; dialogue_present: boolean; object_interaction: boolean; motion_complexity: string; camera_motion: string; quality_threshold: string; budget_limit: string | null; status: string };
export type Character = { id: string; series_id: string; name: string; description: string; visual_reference_url: string; notes: string };
export type CharacterState = { id: string; character_id: string; episode_start: number; episode_end: number; hairstyle: string; wardrobe: string; injury_state: string; props: string; notes: string };
export type ShotSpec = { shot_id: string; series_id: string; saved: boolean; version: number; description: string; shot_type: string; duration_seconds: string; number_of_characters: number; dialogue_present: boolean; object_interaction: boolean; motion_complexity: string; camera_motion: string; quality_requirement: string; budget_limit_usd: string | null; character_ids: string[]; location: string; action: string; dialogue: string; continuity_notes: string };
export type Recommendation = { id: string; shot_id: string; spec_version: number; provider: string; model: string; reason: string; estimated_cost: string; confidence: string; rule_version: string; is_mock: boolean; created_at: string };
export type Review = { id: string; generation_attempt_id: string; reviewer_id: string; decision: "accepted" | "rejected"; failure_reason: string | null; notes: string; created_at: string };
export type Attempt = { id: string; shot_id: string; attempt_number: number; provider: string; model: string; prompt: string; creative_direction: string | null; prompt_source: string; shot_snapshot: Record<string, unknown>; status: string; provider_job_id: string | null; output_url: string | null; output_media_type: string | null; estimated_cost: string; actual_cost: string | null; cost_kind: string | null; generation_time_seconds: string | null; error_message: string | null; created_at: string; completed_at: string | null; review: Review | null };
export type ReviewQueueItem = { attempt: Attempt; shot: Shot; series_title: string; episode_number: number; scene_number: number };
export type Provider = { name: string; models: string[]; max_duration_seconds: string; media_type: string; is_mock: boolean };
export type Estimate = { provider: string; model: string; estimated_cost: string; budget_limit: string | null; over_budget: boolean };
export type ProductionSummary = { total_shots: number; attempted_shots: number; accepted_shots: number; pending_shots: number; generation_attempts: number; reviewed_attempts: number; rejected_attempts: number; retries: number; chargeable_attempts: number; first_pass_reviewed_shots: number; first_pass_accepted_shots: number; total_spend: string; retry_spend: string; retry_waste: string; average_cost_per_attempted_shot: string | null; cost_per_accepted_shot: string | null; first_pass_acceptance_rate: string | null; retries_per_shot: string | null; average_attempt_cost: string | null; spend_by_kind: Record<string, string> };
export type ProviderPerformance = { provider: string; model: string | null; attempts: number; reviewed_attempts: number; accepted_attempts: number; rejected_attempts: number; accepted_shots: number; chargeable_attempts: number; total_spend: string; spend_by_kind: Record<string, string>; acceptance_rate: string | null; average_attempt_cost: string | null; cost_per_accepted_shot: string | null; average_generation_time_seconds: string | null };
export type FailureReasonMetric = { reason: string; rejected_attempts: number; waste: string };
export type SeriesSpend = { series_id: string; title: string; shots: number; accepted_shots: number; attempts: number; retries: number; total_spend: string; retry_waste: string; cost_per_accepted_shot: string | null };
export type EpisodeSpend = { episode_id: string; series_id: string; series_title: string; episode_number: number; title: string; shots: number; accepted_shots: number; attempts: number; retries: number; total_spend: string; retry_waste: string; cost_per_accepted_shot: string | null };
export type AnalyticsReport = { scope: { workspace_id: string; series_id: string | null; series_title: string | null }; generated_at: string; summary: ProductionSummary; series: SeriesSpend[]; providers: ProviderPerformance[]; models: ProviderPerformance[]; failures: FailureReasonMetric[]; episodes: EpisodeSpend[] };

const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export async function request<T>(path: string, session?: Session | null, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...(session ? { "X-Workspace-Id": session.workspaceId, "X-User-Id": session.userId } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function json(method: "POST" | "PATCH" | "PUT", body: object): RequestInit {
  return { method, body: JSON.stringify(body) };
}
