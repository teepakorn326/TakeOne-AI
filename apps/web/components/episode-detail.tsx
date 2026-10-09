"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorMessage, SessionNeeded, Status } from "@/components/feedback";
import { json, request, type Episode, type Scene, type Shot } from "@/lib/api";
import { useSession } from "@/lib/session";

export function EpisodeDetail({ seriesId, episodeId }: { seriesId: string; episodeId: string }) {
  const { session } = useSession();
  const [episode, setEpisode] = useState<Episode | null>(null);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [shots, setShots] = useState<Record<string, Shot[]>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!session) return;
    Promise.all([request<Episode>(`/episodes/${episodeId}`, session), request<Scene[]>(`/episodes/${episodeId}/scenes`, session)])
      .then(async ([ep, sceneList]) => {
        setEpisode(ep); setScenes(sceneList);
        const entries = await Promise.all(sceneList.map(async scene => [scene.id, await request<Shot[]>(`/scenes/${scene.id}/shots`, session)] as const));
        setShots(Object.fromEntries(entries));
      }).catch(e => setError(e.message));
  }, [episodeId, session]);

  async function createScene(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!session) return; setBusy(true); setError(null);
    const form = event.currentTarget; const data = new FormData(form);
    try {
      const item = await request<Scene>(`/episodes/${episodeId}/scenes`, session, json("POST", { scene_number: Number(data.get("number")), location: data.get("location"), time_of_day: data.get("time"), description: data.get("description") }));
      setScenes(current => [...current, item].sort((a, b) => a.scene_number - b.scene_number)); setShots(current => ({ ...current, [item.id]: [] })); form.reset();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  async function createShot(event: FormEvent<HTMLFormElement>, sceneId: string) {
    event.preventDefault(); if (!session) return; setBusy(true); setError(null);
    const form = event.currentTarget; const data = new FormData(form);
    try {
      const item = await request<Shot>(`/scenes/${sceneId}/shots`, session, json("POST", { shot_number: Number(data.get("number")), duration_seconds: data.get("duration"), description: data.get("description"), shot_type: data.get("type") }));
      setShots(current => ({ ...current, [sceneId]: [...(current[sceneId] ?? []), item].sort((a, b) => a.shot_number - b.shot_number) })); form.reset();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  if (session === undefined) return <p className="text-zinc-400">Loading…</p>;
  if (!session) return <SessionNeeded />;
  return <div className="space-y-7">
    <Link href={`/series/${seriesId}`} className="text-sm text-zinc-400 hover:text-white">← Series overview</Link>
    <div><p className="mb-1 text-xs font-semibold uppercase tracking-widest text-zinc-500">Episode {episode?.episode_number}</p><h1 className="text-3xl font-semibold">{episode?.title ?? "Loading…"}</h1><p className="mt-1 text-sm text-zinc-400">Plan scenes and their required shots.</p></div>
    <ErrorMessage message={error} />
    <div className="grid gap-6 lg:grid-cols-[1fr_340px]"><div className="space-y-4">{scenes.length === 0 ? <EmptyState>No scenes yet.</EmptyState> : scenes.map(scene => <Card key={scene.id}><CardHeader><div className="flex items-center justify-between"><div><p className="text-xs text-zinc-500">SCENE {String(scene.scene_number).padStart(2, "0")}</p><h2 className="font-semibold">{scene.location || "Location not set"}</h2><p className="text-sm text-zinc-500">{scene.time_of_day} {scene.description}</p></div><span className="text-xs text-zinc-500">{(shots[scene.id] ?? []).length} {(shots[scene.id] ?? []).length === 1 ? "shot" : "shots"}</span></div></CardHeader><CardContent className="space-y-4">
      <div className="space-y-2">{(shots[scene.id] ?? []).map(shot => <Link key={shot.id} href={`/shots/${shot.id}`} className="flex items-center justify-between rounded-md border border-zinc-800 px-3 py-2 hover:border-zinc-600"><div><span className="mr-3 text-xs text-zinc-500">SHOT {shot.shot_number}</span><span className="text-sm">{shot.description || shot.shot_type || "Untitled shot"}</span></div><Status value={shot.status} /></Link>)}</div>
      <form onSubmit={e => createShot(e, scene.id)} className="grid gap-2 border-t border-zinc-800 pt-4 sm:grid-cols-[80px_90px_1fr_1fr_auto]"><Input name="number" type="number" min="1" placeholder="#" required /><Input name="duration" type="number" min="0.01" step="0.01" placeholder="Seconds" required /><Input name="type" placeholder="Shot type" /><Input name="description" placeholder="Shot description" /><Button size="sm" disabled={busy}>Add shot</Button></form>
    </CardContent></Card>)}</div>
    <Card className="h-fit"><CardHeader><h2 className="font-semibold">New scene</h2></CardHeader><CardContent><form onSubmit={createScene} className="space-y-3"><Input name="number" type="number" min="1" placeholder="Scene number" required /><Input name="location" placeholder="Location" /><Input name="time" placeholder="Time of day" /><textarea name="description" placeholder="Scene description" rows={3} className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm outline-none focus:border-zinc-400" /><Button disabled={busy}>Add scene</Button></form></CardContent></Card></div>
  </div>;
}
