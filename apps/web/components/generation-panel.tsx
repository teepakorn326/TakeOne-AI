"use client";

import { FormEvent, useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { ErrorMessage, Status } from "@/components/feedback";
import { json, request, type Attempt, type Estimate, type Provider, type Recommendation, type Review, type Session, type Shot, type ShotSpec } from "@/lib/api";

const activeStatuses = new Set(["queued", "submitting", "running"]);

export function GenerationPanel({ shot, session, onShotChange, spec, recommendation }: { shot: Shot; session: Session; onShotChange: Dispatch<SetStateAction<Shot | null>>; spec: ShotSpec | null; recommendation: Recommendation | null }) {
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [options, setOptions] = useState<Provider[]>([]);
  const [provider, setProvider] = useState("mock");
  const [model, setModel] = useState("mock-v1");
  const [estimate, setEstimate] = useState<Estimate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [decision, setDecision] = useState<"accepted" | "rejected">("accepted");
  const [failureReason, setFailureReason] = useState("");
  const [reviewNotes, setReviewNotes] = useState("");
  const [failureReasons, setFailureReasons] = useState<string[]>([]);
  const submissionKey = useRef<{ key: string; inputs: string } | null>(null);
  const active = attempts.some(attempt => activeStatuses.has(attempt.status));
  const latest = attempts.at(-1);
  const pendingReview = shot.status === "review" && latest?.status === "review" && !latest.review ? latest : null;

  useEffect(() => {
    setDecision("accepted");
    setFailureReason("");
    setReviewNotes("");
  }, [pendingReview?.id]);

  useEffect(() => {
    Promise.all([
      request<Attempt[]>(`/shots/${shot.id}/attempts`, session),
      request<Provider[]>("/settings/providers", session),
      request<string[]>("/review/failure-reasons", session),
    ]).then(([list, available, reasons]) => { setAttempts(list); setOptions(available); setFailureReasons(reasons); }).catch(e => setError(e.message));
  }, [shot.id, session]);

  useEffect(() => {
    if (shot.status === "rejected" && latest?.review?.decision === "rejected") {
      setProvider(latest.provider);
      setModel(latest.model);
    }
  }, [shot.status, latest?.id, latest?.review?.decision]);

  useEffect(() => {
    if (recommendation && recommendation.spec_version === spec?.version) {
      setProvider(recommendation.provider);
      setModel(recommendation.model);
    }
  }, [recommendation?.id, spec?.version]);

  useEffect(() => {
    request<Estimate>(`/shots/${shot.id}/estimate?provider=${encodeURIComponent(provider)}&model=${encodeURIComponent(model)}`, session)
      .then(setEstimate).catch(e => setError(e.message));
  }, [shot.id, shot.duration_seconds, shot.motion_complexity, shot.quality_threshold, shot.budget_limit, session, provider, model]);

  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => {
      Promise.all([
        request<Attempt[]>(`/shots/${shot.id}/attempts`, session),
        request<Shot>(`/shots/${shot.id}`, session),
      ]).then(([list, currentShot]) => { setAttempts(list); onShotChange(currentShot); setError(null); }).catch(e => setError(e.message));
    }, 1500);
    return () => window.clearInterval(timer);
  }, [active, shot.id, session, onShotChange]);

  async function generate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(null); setNotice(null); setBusy(true);
    const data = new FormData(event.currentTarget);
    const prompt = spec?.saved ? null : String(data.get("prompt") ?? "");
    const creativeDirection = spec?.saved ? String(data.get("creative_direction") ?? "") : null;
    const retrying = shot.status === "rejected";
    const inputs = JSON.stringify({ provider, model, prompt, creativeDirection, specVersion: spec?.version, retrying });
    const key = submissionKey.current?.inputs === inputs ? submissionKey.current.key : window.crypto.randomUUID();
    submissionKey.current = { key, inputs };
    try {
      const attempt = await request<Attempt>(retrying ? `/shots/${shot.id}/retry` : `/shots/${shot.id}/attempts`, session, {
        ...json("POST", { provider, model, ...(spec?.saved ? { creative_direction: creativeDirection } : { prompt }) }),
        headers: { "Idempotency-Key": key },
      });
      submissionKey.current = null;
      setAttempts(current => current.some(item => item.id === attempt.id) ? current : [...current, attempt]);
      onShotChange(current => current ? { ...current, status: attempt.status === "review" ? "review" : "generating" } : current);
      setNotice(`Attempt ${attempt.attempt_number} submitted.`);
    } catch (e) {
      const message = (e as Error).message;
      if (!message.includes("retry with the same Idempotency-Key")) submissionKey.current = null;
      setError(message);
    } finally { setBusy(false); }
  }

  async function cancel(attemptId: string) {
    setError(null); setNotice(null);
    try {
      await request(`/attempts/${attemptId}/cancel`, session, json("POST", {}));
      setNotice("Cancellation requested.");
    } catch (e) { setError((e as Error).message); }
  }

  async function review(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!pendingReview) return;
    setReviewBusy(true); setError(null); setNotice(null);
    try {
      const result = await request<Review>(`/attempts/${pendingReview.id}/reviews`, session, json("POST", {
        decision, failure_reason: decision === "rejected" ? failureReason : null, notes: reviewNotes,
      }));
      setAttempts(current => current.map(item => item.id === pendingReview.id ? { ...item, review: result } : item));
      onShotChange(current => current ? { ...current, status: result.decision } : current);
      setNotice(result.decision === "accepted" ? "Shot accepted." : "Rejection recorded. You can retry with the same or another provider.");
    } catch (cause) { setError((cause as Error).message); }
    finally { setReviewBusy(false); }
  }

  const canGenerate = ["ready", "failed", "rejected"].includes(shot.status);
  const selectedProvider = options.find(item => item.name === provider);
  return <div className="space-y-5">
    {pendingReview && <Card><CardHeader><div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="font-semibold">Review generated result</h2><p className="mt-1 text-sm text-zinc-500">Inspect attempt {pendingReview.attempt_number} before deciding.</p></div><Status value="review" /></div></CardHeader><CardContent className="grid gap-6 lg:grid-cols-2">
      <div className="space-y-3"><div className="overflow-hidden rounded-md border border-zinc-800 bg-zinc-950">{pendingReview.output_url && (pendingReview.output_media_type?.startsWith("video/") ? <video src={pendingReview.output_url} controls className="w-full" /> : <img src={pendingReview.output_url} alt="Generated result to review" className="w-full" />)}</div><p className="text-xs text-zinc-500">{pendingReview.provider} / {pendingReview.model} · Attempt {pendingReview.attempt_number} · {pendingReview.cost_kind === "simulated" ? "Simulated" : "Recorded"} cost ${Number(pendingReview.actual_cost ?? pendingReview.estimated_cost).toFixed(2)}</p></div>
      <div className="space-y-4"><div className="rounded-md border border-zinc-800 bg-zinc-950/50 p-4 text-sm"><p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Shot requirements</p><p className="mt-2 text-zinc-200">{shot.description || "No description"}</p><div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-400"><span>{shot.duration_seconds}s</span><span>{shot.shot_type || "Unspecified shot type"}</span><span>{shot.motion_complexity} motion</span><span>{shot.camera_motion} camera</span></div><p className="mt-3 text-xs text-zinc-500">Prompt: {pendingReview.prompt}</p></div>
        <form onSubmit={review} className="space-y-4"><fieldset className="space-y-2"><legend className="text-xs font-medium uppercase tracking-wide text-zinc-500">Decision</legend><div className="flex gap-4 text-sm"><label className="flex items-center gap-2"><input type="radio" name="decision" checked={decision === "accepted"} onChange={() => setDecision("accepted")} /> Accept</label><label className="flex items-center gap-2"><input type="radio" name="decision" checked={decision === "rejected"} onChange={() => setDecision("rejected")} /> Reject</label></div></fieldset>
          {decision === "rejected" && <label className="block text-xs font-medium uppercase tracking-wide text-zinc-500">Failure reason<select value={failureReason} onChange={event => setFailureReason(event.target.value)} required className="mt-1.5 h-9 w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 text-sm normal-case text-zinc-100"><option value="">Select a reason</option>{failureReasons.map(reason => <option key={reason} value={reason}>{reason.replaceAll("_", " ")}</option>)}</select></label>}
          <label className="block text-xs font-medium uppercase tracking-wide text-zinc-500">Notes (optional)<textarea value={reviewNotes} onChange={event => setReviewNotes(event.target.value)} rows={3} maxLength={5000} className="mt-1.5 w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm normal-case text-zinc-100 outline-none focus:border-zinc-400" /></label><Button disabled={reviewBusy || (decision === "rejected" && !failureReason)}>{decision === "accepted" ? "Accept shot" : "Record rejection"}</Button></form>
      </div>
    </CardContent></Card>}
    <Card><CardHeader><div className="flex items-center justify-between"><div><h2 className="font-semibold">{shot.status === "rejected" ? "Retry shot" : "Generate shot"}</h2><p className="mt-1 text-sm text-zinc-500">The mock providers test the workflow and record simulated cost.</p></div><Status value={shot.status} /></div></CardHeader><CardContent className="space-y-4">
      <ErrorMessage message={error} />{notice && <p role="status" className="text-sm text-emerald-400">{notice}</p>}
      {canGenerate ? <form key={`${shot.id}-${shot.status}-${latest?.id ?? "first"}`} onSubmit={generate} className="space-y-4">
        {shot.status === "rejected" && <p className="rounded-md border border-amber-900 bg-amber-950/30 px-3 py-2 text-sm text-amber-200">Retry attempt {latest?.attempt_number ?? 0}. Keep the provider or select another mock provider to compare outcomes.</p>}
        <div className="grid gap-4 sm:grid-cols-2"><label className="space-y-1.5 text-xs font-medium uppercase tracking-wide text-zinc-500">Provider<select value={provider} onChange={event => { const next = options.find(item => item.name === event.target.value); setProvider(event.target.value); setModel(next?.models[0] ?? ""); }} className="mt-1 h-9 w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 text-sm normal-case text-zinc-100">{options.map(item => <option key={item.name} value={item.name}>{item.name}{item.is_mock ? " (mock)" : ""}</option>)}</select></label>
          <label className="space-y-1.5 text-xs font-medium uppercase tracking-wide text-zinc-500">Model<select value={model} onChange={event => setModel(event.target.value)} className="mt-1 h-9 w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 text-sm normal-case text-zinc-100">{selectedProvider?.models.map(item => <option key={item} value={item}>{item}</option>)}</select></label></div>
        {spec?.saved ? <label className="block text-xs font-medium uppercase tracking-wide text-zinc-500">Creative direction (optional)<textarea name="creative_direction" defaultValue={shot.status === "rejected" ? latest?.creative_direction ?? "" : ""} rows={3} maxLength={5000} className="mt-1.5 w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm normal-case text-zinc-100 outline-none focus:border-zinc-400" /><span className="mt-1 block normal-case text-zinc-500">Prompt compiled from saved shot spec v{spec.version}, character continuity, and this direction.</span></label> : <label className="block text-xs font-medium uppercase tracking-wide text-zinc-500">Prompt<textarea name="prompt" defaultValue={shot.status === "rejected" ? latest?.prompt : shot.description} required rows={4} maxLength={10000} className="mt-1.5 w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm normal-case text-zinc-100 outline-none focus:border-zinc-400" /></label>}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-zinc-800 pt-4"><div className="text-sm text-zinc-400">Estimated cost: <strong className="text-zinc-100">{estimate ? `$${Number(estimate.estimated_cost).toFixed(2)}` : "Loading…"}</strong>{estimate?.budget_limit && <span className="ml-2 text-xs">Budget ${Number(estimate.budget_limit).toFixed(2)}</span>}{estimate?.over_budget && <span className="ml-2 text-red-400">Over budget</span>}</div><Button disabled={busy || !estimate || estimate.over_budget || options.length === 0}>{shot.status === "rejected" ? "Retry shot" : "Generate"}</Button></div>
      </form> : <p className="text-sm text-zinc-500">{shot.status === "draft" ? "Mark this shot Ready above to generate." : shot.status === "review" ? "Generation finished. Review the result above." : shot.status === "accepted" ? "This shot has been accepted." : "Generation is in progress."}</p>}
    </CardContent></Card>
    <Card><CardHeader><h2 className="font-semibold">Generation attempts <span className="ml-2 font-normal text-zinc-500">{attempts.length}</span></h2></CardHeader><CardContent className="space-y-4">{attempts.length === 0 ? <p className="text-sm text-zinc-500">No attempts yet.</p> : attempts.map(attempt => <div key={attempt.id} className="rounded-md border border-zinc-800 p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="font-medium">Attempt {attempt.attempt_number} <span className="ml-2 text-sm font-normal text-zinc-500">{attempt.provider} / {attempt.model}</span></p><p className="mt-1 text-xs text-zinc-500">{new Date(attempt.created_at).toLocaleString()}</p></div><Status value={attempt.review?.decision ?? attempt.status} /></div>
      <div className="mt-3 flex flex-wrap items-center gap-4 text-sm text-zinc-400"><span>Estimate ${Number(attempt.estimated_cost).toFixed(2)}</span>{attempt.actual_cost !== null && <span>{attempt.cost_kind === "simulated" ? "Simulated" : "Actual"} cost ${Number(attempt.actual_cost).toFixed(2)}</span>}{attempt.generation_time_seconds !== null && <span>{Number(attempt.generation_time_seconds).toFixed(1)}s</span>}</div>
      <p className="mt-2 text-xs text-zinc-500">{attempt.prompt_source === "structured" ? `Structured prompt · spec v${(attempt.shot_snapshot.structured_spec as { version?: number } | undefined)?.version ?? "?"}` : "Manual prompt"}</p>
      {attempt.review && <div className="mt-3 rounded-md border border-zinc-800 bg-zinc-950/50 px-3 py-2 text-sm"><span className={attempt.review.decision === "accepted" ? "text-emerald-400" : "text-amber-400"}>{attempt.review.decision === "accepted" ? "Accepted" : "Rejected"}</span>{attempt.review.failure_reason && <span className="ml-2 text-zinc-400">· {attempt.review.failure_reason.replaceAll("_", " ")}</span>}{attempt.review.notes && <p className="mt-1 text-zinc-400">{attempt.review.notes}</p>}</div>}
      {attempt.error_message && <p className="mt-3 text-sm text-red-400">{attempt.error_message}</p>}
      {attempt.output_url && <details className="mt-3 text-sm text-zinc-400"><summary className="cursor-pointer hover:text-zinc-200">View output</summary><div className="mt-3 overflow-hidden rounded-md border border-zinc-800 bg-zinc-950">{attempt.output_media_type?.startsWith("video/") ? <video src={attempt.output_url} controls className="w-full" /> : <img src={attempt.output_url} alt={`Attempt ${attempt.attempt_number} output`} className="w-full" />}</div></details>}
      {activeStatuses.has(attempt.status) && <Button type="button" variant="secondary" size="sm" className="mt-4" onClick={() => cancel(attempt.id)}>Cancel</Button>}
    </div>)}</CardContent></Card>
  </div>;
}
