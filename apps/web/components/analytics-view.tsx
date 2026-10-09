"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { EmptyState, ErrorMessage, SessionNeeded } from "@/components/feedback";
import { request, type AnalyticsReport, type EpisodeSpend, type FailureReasonMetric, type ProviderPerformance, type Series, type SeriesSpend } from "@/lib/api";
import { useSession } from "@/lib/session";

const money = (value: string | null) => value === null ? "—" : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 4 }).format(Number(value));
const percent = (value: string | null) => value === null ? "—" : `${(Number(value) * 100).toFixed(1)}%`;
const count = (value: number) => new Intl.NumberFormat("en-US").format(value);
const plural = (value: number, name: string) => `${count(value)} ${name}${value === 1 ? "" : "s"}`;
const cell = "whitespace-nowrap px-4 py-3 text-right text-sm text-zinc-300";
const head = "whitespace-nowrap px-4 py-3 text-right text-xs font-medium uppercase tracking-wide text-zinc-500";

function MetricCard({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return <Card><CardContent className="space-y-1"><p className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</p><p className="text-2xl font-semibold tabular-nums text-zinc-100">{value}</p>{detail && <p className="text-xs text-zinc-500">{detail}</p>}</CardContent></Card>;
}

function SummaryCards({ report }: { report: AnalyticsReport }) {
  const summary = report.summary;
  return <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
    <MetricCard label="Generation spend" value={money(summary.total_spend)} detail={plural(summary.chargeable_attempts, "chargeable attempt")} />
    <MetricCard label="Cost per attempted shot" value={money(summary.average_cost_per_attempted_shot)} detail={`${plural(summary.attempted_shots, "shot")} with an attempt`} />
    <MetricCard label="Cost per accepted shot" value={money(summary.cost_per_accepted_shot)} detail={plural(summary.accepted_shots, "accepted shot")} />
    <MetricCard label="Retry waste" value={money(summary.retry_waste)} detail="Cost of rejected attempts" />
    <MetricCard label="First-pass acceptance" value={percent(summary.first_pass_acceptance_rate)} detail={`${summary.first_pass_accepted_shots} of ${plural(summary.first_pass_reviewed_shots, "reviewed first attempt")}`} />
    <MetricCard label="Total shots" value={count(summary.total_shots)} />
    <MetricCard label="Accepted shots" value={count(summary.accepted_shots)} />
    <MetricCard label="Not yet accepted" value={count(summary.pending_shots)} />
    <MetricCard label="Retries" value={count(summary.retries)} detail={`${summary.retries_per_shot === null ? "—" : Number(summary.retries_per_shot).toFixed(2)} per attempted shot · ${money(summary.retry_spend)} spent`} />
  </div>;
}

function SpendKinds({ report }: { report: AnalyticsReport }) {
  const entries = Object.entries(report.summary.spend_by_kind).filter(([, amount]) => Number(amount) > 0);
  return <p className="text-sm text-zinc-400">{entries.length === 0 ? "No cost recorded yet." : <>Spend composition: {entries.map(([kind, amount], index) => <span key={kind}>{index > 0 ? " · " : ""}<strong className="font-medium text-zinc-200">{kind}</strong> {money(amount)}</span>)}</>}{Number(report.summary.spend_by_kind.simulated ?? 0) > 0 && <span className="ml-1">Mock costs are simulated.</span>}{Number(report.summary.spend_by_kind.estimated ?? 0) > 0 && <span className="ml-1">Estimated costs are provisional.</span>}</p>;
}

function SeriesTable({ rows }: { rows: SeriesSpend[] }) {
  return <Card><CardHeader><h2 className="font-semibold">Series overview</h2><p className="mt-1 text-xs text-zinc-500">Spend includes every recorded attempt in each series.</p></CardHeader><CardContent className="p-0">{rows.length === 0 ? <div className="p-5"><EmptyState>No series yet.</EmptyState></div> : <div className="overflow-x-auto"><table className="w-full"><thead className="border-b border-zinc-800"><tr><th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-zinc-500">Series</th><th className={head}>Shots</th><th className={head}>Accepted</th><th className={head}>Attempts</th><th className={head}>Spend</th><th className={head}>Retry waste</th><th className={head}>Cost / accepted</th></tr></thead><tbody>{rows.map(row => <tr key={row.series_id} className="border-b border-zinc-800/70 last:border-0"><td className="px-4 py-3 text-sm"><Link href={`/series/${row.series_id}`} className="font-medium text-zinc-100 hover:underline">{row.title}</Link></td><td className={cell}>{row.shots}</td><td className={cell}>{row.accepted_shots}</td><td className={cell}>{row.attempts}</td><td className={cell}>{money(row.total_spend)}</td><td className={cell}>{money(row.retry_waste)}</td><td className={cell}>{money(row.cost_per_accepted_shot)}</td></tr>)}</tbody></table></div>}</CardContent></Card>;
}

function ProviderTable({ rows, models = false }: { rows: ProviderPerformance[]; models?: boolean }) {
  return <Card><CardHeader><h2 className="font-semibold">{models ? "Model economics" : "Provider performance"}</h2><p className="mt-1 text-xs text-zinc-500">Acceptance uses reviewed attempts. Cost per accepted shot attributes each row’s spend to shots accepted from that provider or model.</p></CardHeader><CardContent className="p-0">{rows.length === 0 ? <div className="p-5"><EmptyState>No provider attempts yet.</EmptyState></div> : <div className="overflow-x-auto"><table className="w-full"><thead className="border-b border-zinc-800"><tr><th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-zinc-500">{models ? "Provider / model" : "Provider"}</th><th className={head}>Attempts</th><th className={head}>Reviewed</th><th className={head}>Accepted</th><th className={head}>Accept rate</th><th className={head}>Spend</th><th className={head}>Cost basis</th><th className={head}>Avg attempt</th><th className={head}>Cost / accepted</th><th className={head}>Avg time</th></tr></thead><tbody>{rows.map(row => <tr key={`${row.provider}:${row.model ?? "all"}`} className="border-b border-zinc-800/70 last:border-0"><td className="whitespace-nowrap px-4 py-3 text-sm font-medium text-zinc-100">{row.provider}{models && <span className="font-normal text-zinc-500"> / {row.model}</span>}</td><td className={cell}>{row.attempts}</td><td className={cell}>{row.reviewed_attempts}</td><td className={cell}>{row.accepted_attempts}</td><td className={cell}>{percent(row.acceptance_rate)}</td><td className={cell}>{money(row.total_spend)}</td><td className="min-w-32 px-4 py-3 text-right text-xs text-zinc-400">{Object.entries(row.spend_by_kind).filter(([, amount]) => Number(amount) > 0).map(([kind, amount]) => `${kind} ${money(amount)}`).join(" · ") || "—"}</td><td className={cell}>{money(row.average_attempt_cost)}</td><td className={cell}>{money(row.cost_per_accepted_shot)}</td><td className={cell}>{row.average_generation_time_seconds === null ? "—" : `${Number(row.average_generation_time_seconds).toFixed(1)}s`}</td></tr>)}</tbody></table></div>}</CardContent></Card>;
}

function FailureReasons({ rows }: { rows: FailureReasonMetric[] }) {
  const largest = Math.max(0, ...rows.map(row => row.rejected_attempts));
  return <Card><CardHeader><h2 className="font-semibold">Failure reasons</h2><p className="mt-1 text-xs text-zinc-500">Each rejected review contributes one reason. Waste is its recorded attempt cost.</p></CardHeader><CardContent>{rows.length === 0 ? <EmptyState>No rejected attempts yet.</EmptyState> : <div className="space-y-4">{rows.map(row => <div key={row.reason}><div className="mb-1.5 flex items-center justify-between gap-3 text-sm"><span className="capitalize text-zinc-200">{row.reason.replaceAll("_", " ")}</span><span className="whitespace-nowrap tabular-nums text-zinc-400">{row.rejected_attempts} · {money(row.waste)}</span></div><div className="h-2 overflow-hidden rounded-full bg-zinc-800"><div className="h-full rounded-full bg-amber-500/70" style={{ width: `${largest ? row.rejected_attempts / largest * 100 : 0}%` }} /></div></div>)}</div>}</CardContent></Card>;
}

function EpisodeTable({ rows }: { rows: EpisodeSpend[] }) {
  return <Card><CardHeader><h2 className="font-semibold">Episode cost</h2></CardHeader><CardContent className="p-0">{rows.length === 0 ? <div className="p-5"><EmptyState>No episodes yet.</EmptyState></div> : <div className="overflow-x-auto"><table className="w-full"><thead className="border-b border-zinc-800"><tr><th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-zinc-500">Episode</th><th className={head}>Shots</th><th className={head}>Accepted</th><th className={head}>Retries</th><th className={head}>Spend</th><th className={head}>Retry waste</th><th className={head}>Cost / accepted</th></tr></thead><tbody>{rows.map(row => <tr key={row.episode_id} className="border-b border-zinc-800/70 last:border-0"><td className="min-w-48 px-4 py-3 text-sm"><Link href={`/series/${row.series_id}/episodes/${row.episode_id}`} className="font-medium text-zinc-100 hover:underline">{row.series_title} · E{row.episode_number} {row.title}</Link></td><td className={cell}>{row.shots}</td><td className={cell}>{row.accepted_shots}</td><td className={cell}>{row.retries}</td><td className={cell}>{money(row.total_spend)}</td><td className={cell}>{money(row.retry_waste)}</td><td className={cell}>{money(row.cost_per_accepted_shot)}</td></tr>)}</tbody></table></div>}</CardContent></Card>;
}

export function AnalyticsView({ view }: { view: "dashboard" | "analytics" }) {
  const { session } = useSession();
  const [series, setSeries] = useState<Series[]>([]);
  const [seriesId, setSeriesId] = useState("");
  const [report, setReport] = useState<AnalyticsReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    request<Series[]>("/series", session).then(result => { if (!cancelled) setSeries(result); }).catch(cause => { if (!cancelled) setError((cause as Error).message); });
    return () => { cancelled = true; };
  }, [session]);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    setLoading(true); setReport(null);
    const query = seriesId ? `?series_id=${encodeURIComponent(seriesId)}` : "";
    request<AnalyticsReport>(`/dashboard${query}`, session)
      .then(result => { if (!cancelled) { setReport(result); setError(null); } })
      .catch(cause => { if (!cancelled) setError((cause as Error).message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [session, seriesId, revision]);

  if (session === undefined) return <p className="text-zinc-400">Loading…</p>;
  if (!session) return <SessionNeeded />;
  return <div className="space-y-6">
    <div className="flex flex-wrap items-end justify-between gap-4"><div><p className="mb-1 text-xs font-semibold uppercase tracking-widest text-zinc-500">{session.workspaceName} · Production economics</p><h1 className="text-3xl font-semibold">{view === "dashboard" ? "Dashboard" : "Analytics"}</h1><p className="mt-2 text-sm text-zinc-400">{view === "dashboard" ? "Track acceptance, spend, and generation waste." : "Compare provider economics and see where rejections cost the most."}</p></div><div className="flex flex-wrap items-end gap-2"><label className="text-xs font-medium uppercase tracking-wide text-zinc-500">Scope<select value={seriesId} onChange={event => setSeriesId(event.target.value)} className="mt-1 block h-9 min-w-40 max-w-56 rounded-md border border-zinc-700 bg-zinc-900 px-3 text-sm normal-case text-zinc-100"><option value="">All series</option>{series.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label><Button type="button" variant="secondary" onClick={() => setRevision(value => value + 1)}>Refresh</Button></div></div>
    <ErrorMessage message={error} />
    {loading ? <p className="text-sm text-zinc-500">Calculating production metrics…</p> : report && <>
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-zinc-500"><span>Scope: {report.scope.series_title ?? "All series"}</span><span>Computed {new Date(report.generated_at).toLocaleString()}</span></div>
      <SpendKinds report={report} />
      <SummaryCards report={report} />
      {view === "dashboard" ? <>
        <SeriesTable rows={report.series} />
        <ProviderTable rows={report.providers} />
        <div className="flex justify-end"><Link href="/analytics" className="text-sm text-zinc-300 underline hover:text-white">Explore detailed analytics →</Link></div>
        <FailureReasons rows={report.failures} />
        <EpisodeTable rows={report.episodes} />
      </> : <>
        <ProviderTable rows={report.providers} />
        <ProviderTable rows={report.models} models />
        <FailureReasons rows={report.failures} />
        <EpisodeTable rows={report.episodes} />
        <SeriesTable rows={report.series} />
      </>}
      <p className="text-xs text-zinc-500">Acceptance rates exclude pending reviews. Provider cost per accepted shot attributes each provider’s total spend to shots it got accepted; mixed-provider retries make this different from the studio-wide cost per accepted shot.</p>
    </>}
  </div>;
}
