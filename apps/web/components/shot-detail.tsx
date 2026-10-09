"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ErrorMessage, SessionNeeded, Status } from "@/components/feedback";
import { json, request, type Recommendation, type Shot, type ShotSpec } from "@/lib/api";
import { useSession } from "@/lib/session";
import { GenerationPanel } from "@/components/generation-panel";
import { ShotSpecPanel } from "@/components/shot-spec-panel";

const label = "block mb-1.5 text-xs font-medium uppercase tracking-wide text-zinc-500";

export function ShotDetail({ id }: { id: string }) {
  const { session } = useSession();
  const [shot, setShot] = useState<Shot | null>(null);
  const [spec, setSpec] = useState<ShotSpec | null>(null);
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (session) Promise.all([request<Shot>(`/shots/${id}`, session), request<ShotSpec>(`/shots/${id}/spec`, session)]).then(([s, structured]) => { setShot(s); setSpec(structured); }).catch(e => setError(e.message)); }, [id, session]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!session || !shot) return; setBusy(true); setSaved(false); setError(null);
    const data = new FormData(event.currentTarget);
    try {
      const updated = await request<Shot>(`/shots/${id}`, session, json("PATCH", {
        description: data.get("description"), shot_type: data.get("type"), duration_seconds: data.get("duration"),
        number_of_characters: Number(data.get("characters")), dialogue_present: data.has("dialogue"),
        object_interaction: data.has("interaction"), motion_complexity: data.get("motion"),
        camera_motion: data.get("camera"), quality_threshold: data.get("quality"),
        budget_limit: data.get("budget") || null,
        ...(shot.status === "rejected" ? {} : { status: data.get("status") }),
      }));
      setShot(updated); setSpec(await request<ShotSpec>(`/shots/${id}/spec`, session)); setRecommendation(null); setSaved(true);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  if (session === undefined) return <p className="text-zinc-400">Loading…</p>;
  if (!session) return <SessionNeeded />;
  return <div className="max-w-6xl space-y-7">
    <Link href="/series" className="text-sm text-zinc-400 hover:text-white">← Production</Link>
    <div className="flex items-center justify-between"><div><p className="mb-1 text-xs font-semibold uppercase tracking-widest text-zinc-500">Shot {shot?.shot_number}</p><h1 className="text-3xl font-semibold">Shot requirements</h1></div>{shot && <Status value={shot.status} />}</div>
    <ErrorMessage message={error} />{saved && <p className="text-sm text-emerald-400">Shot saved.</p>}
    {shot && <Card><CardHeader><h2 className="font-semibold">Shot plan</h2><p className="text-sm text-zinc-500">Set requirements and budget before generating or retrying.</p></CardHeader><CardContent>{!["draft", "ready", "failed", "rejected"].includes(shot.status) ? <p className="text-sm text-zinc-400">This plan is locked during generation and review, and after acceptance.</p> : <form key={shot.id} onSubmit={save} className="space-y-5">
      <div><label className={label}>Description</label><textarea name="description" defaultValue={shot.description} rows={4} className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm outline-none focus:border-zinc-400" /></div>
      <div className="grid gap-4 sm:grid-cols-3"><div><label className={label}>Shot type</label><Input name="type" defaultValue={shot.shot_type} placeholder="Close-up" /></div><div><label className={label}>Duration (seconds)</label><Input name="duration" type="number" min="0.01" step="0.01" required defaultValue={shot.duration_seconds} /></div><div><label className={label}>Characters</label><Input name="characters" type="number" min="0" required defaultValue={shot.number_of_characters} /></div></div>
      <div className="grid gap-4 sm:grid-cols-3"><div><label className={label}>Motion complexity</label><select name="motion" defaultValue={shot.motion_complexity} className="h-9 w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 text-sm"><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select></div><div><label className={label}>Camera motion</label><Input name="camera" defaultValue={shot.camera_motion} /></div><div><label className={label}>Quality requirement</label><select name="quality" defaultValue={shot.quality_threshold} className="h-9 w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 text-sm"><option value="draft">Draft</option><option value="standard">Standard</option><option value="high">High</option></select></div></div>
      <div className="flex gap-6 text-sm text-zinc-300"><label className="flex items-center gap-2"><input type="checkbox" name="dialogue" defaultChecked={shot.dialogue_present} /> Dialogue</label><label className="flex items-center gap-2"><input type="checkbox" name="interaction" defaultChecked={shot.object_interaction} /> Object interaction</label></div>
      <div className="grid gap-4 sm:grid-cols-2"><div><label className={label}>Budget limit (USD)</label><Input name="budget" type="number" min="0" step="0.0001" defaultValue={shot.budget_limit ?? ""} placeholder="Optional" /></div>{shot.status === "rejected" ? <div><span className={label}>Status</span><p className="flex h-9 items-center text-sm text-zinc-400">Rejected · retry below after saving changes</p></div> : <div><label className={label}>Status</label><select name="status" defaultValue={shot.status} className="h-9 w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 text-sm"><option value="draft">Draft</option><option value="ready">Ready</option></select></div>}</div>
      <div className="border-t border-zinc-800 pt-5"><Button disabled={busy}>Save shot</Button></div>
    </form>}</CardContent></Card>}
    {shot && <ShotSpecPanel shot={shot} session={session} spec={spec} onSpecChange={value => { setSpec(value); setRecommendation(null); request<Shot>(`/shots/${id}`, session).then(setShot).catch(e => setError(e.message)); }} onRecommendation={setRecommendation} />}
    {shot && <GenerationPanel shot={shot} session={session} onShotChange={setShot} spec={spec} recommendation={recommendation} />}
  </div>;
}
