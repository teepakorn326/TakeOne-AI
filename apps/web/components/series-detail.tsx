"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorMessage, SessionNeeded, Status } from "@/components/feedback";
import { json, request, type Episode, type Series } from "@/lib/api";
import { useSession } from "@/lib/session";
import { CharacterPanel } from "@/components/character-panel";

export function SeriesDetail({ id }: { id: string }) {
  const { session } = useSession();
  const [series, setSeries] = useState<Series | null>(null);
  const [episodes, setEpisodes] = useState<Episode[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (session) Promise.all([request<Series>(`/series/${id}`, session), request<Episode[]>(`/series/${id}/episodes`, session)]).then(([s, e]) => { setSeries(s); setEpisodes(e); }).catch(e => setError(e.message)); }, [id, session]);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!session) return; setBusy(true); setError(null);
    const form = event.currentTarget; const data = new FormData(form);
    try {
      const item = await request<Episode>(`/series/${id}/episodes`, session, json("POST", { episode_number: Number(data.get("number")), title: data.get("title") }));
      setEpisodes(current => [...current, item].sort((a, b) => a.episode_number - b.episode_number)); form.reset();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  if (session === undefined) return <p className="text-zinc-400">Loading…</p>;
  if (!session) return <SessionNeeded />;
  return <div className="space-y-7">
    <Link href="/series" className="text-sm text-zinc-400 hover:text-white">← All series</Link>
    <div><p className="mb-1 text-xs font-semibold uppercase tracking-widest text-zinc-500">Series</p><h1 className="text-3xl font-semibold">{series?.title ?? "Loading…"}</h1><p className="mt-2 max-w-2xl text-sm text-zinc-400">{series?.description}</p></div>
    <ErrorMessage message={error} />
    <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
      <Card><CardHeader><h2 className="font-semibold">Episodes <span className="ml-2 text-sm font-normal text-zinc-500">{episodes.length}</span></h2></CardHeader><CardContent className="space-y-2">{episodes.length === 0 ? <EmptyState>No episodes yet.</EmptyState> : episodes.map(item => <Link key={item.id} href={`/series/${id}/episodes/${item.id}`} className="flex items-center justify-between rounded-md border border-zinc-800 px-4 py-3 hover:border-zinc-600"><div><div className="text-xs text-zinc-500">EP {String(item.episode_number).padStart(2, "0")}</div><div className="font-medium">{item.title}</div></div><Status value={item.status} /></Link>)}</CardContent></Card>
      <Card><CardHeader><h2 className="font-semibold">New episode</h2></CardHeader><CardContent><form onSubmit={create} className="space-y-3"><Input name="number" type="number" min="1" placeholder="Episode number" required /><Input name="title" placeholder="Episode title" required maxLength={200} /><Button disabled={busy}>Add episode</Button></form></CardContent></Card>
    </div>
    <CharacterPanel seriesId={id} session={session} />
  </div>;
}
