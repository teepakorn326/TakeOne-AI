"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { EmptyState, ErrorMessage, SessionNeeded } from "@/components/feedback";
import { request, type ReviewQueueItem } from "@/lib/api";
import { useSession } from "@/lib/session";

export function ReviewQueue() {
  const { session } = useSession();
  const [items, setItems] = useState<ReviewQueueItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const refresh = useCallback(() => {
    if (!session) return;
    setLoading(true);
    request<ReviewQueueItem[]>("/review", session)
      .then(result => { setItems(result); setError(null); })
      .catch(cause => setError((cause as Error).message))
      .finally(() => setLoading(false));
  }, [session]);
  useEffect(() => { refresh(); }, [refresh]);

  if (session === undefined) return <p className="text-zinc-400">Loading…</p>;
  if (!session) return <SessionNeeded />;
  return <div className="max-w-5xl space-y-6">
    <div className="flex flex-wrap items-end justify-between gap-4"><div><p className="mb-1 text-xs font-semibold uppercase tracking-widest text-zinc-500">Production review</p><h1 className="text-3xl font-semibold">Review queue</h1><p className="mt-2 text-sm text-zinc-400">Generation attempts waiting for a human decision.</p></div><Button type="button" variant="secondary" onClick={refresh}>Refresh queue</Button></div>
    <ErrorMessage message={error} />
    {loading ? <p className="text-sm text-zinc-500">Loading queue…</p> : items.length === 0 ? <EmptyState>No shots are waiting for review.</EmptyState> : <div className="grid gap-4">{items.map(item => <Card key={item.attempt.id}><CardHeader><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs uppercase tracking-wide text-zinc-500">{item.series_title} · Episode {item.episode_number} · Scene {item.scene_number}</p><h2 className="mt-1 font-semibold">Shot {item.shot.shot_number} · Attempt {item.attempt.attempt_number}</h2></div><span className="rounded-full border border-amber-800 bg-amber-950/40 px-2 py-0.5 text-xs text-amber-300">Awaiting review</span></div></CardHeader><CardContent className="grid gap-4 sm:grid-cols-[140px_1fr_auto] sm:items-center"><div className="overflow-hidden rounded border border-zinc-800 bg-zinc-950">{item.attempt.output_url && (item.attempt.output_media_type?.startsWith("video/") ? <video src={item.attempt.output_url} className="w-full" muted /> : <img src={item.attempt.output_url} alt="Generation preview" className="w-full" />)}</div><div className="min-w-0"><p className="line-clamp-2 text-sm text-zinc-200">{item.shot.description || item.attempt.prompt}</p><p className="mt-2 text-xs text-zinc-500">{item.attempt.provider} / {item.attempt.model} · {item.attempt.cost_kind === "simulated" ? "Simulated" : "Recorded"} cost ${Number(item.attempt.actual_cost ?? item.attempt.estimated_cost).toFixed(2)}</p></div><Link href={`/shots/${item.shot.id}`} className="inline-flex h-9 items-center justify-center rounded-md bg-zinc-100 px-4 text-sm font-medium text-zinc-900 hover:bg-white">Review shot</Link></CardContent></Card>)}</div>}
  </div>;
}
