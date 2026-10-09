"use client";

import { FormEvent, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { ErrorMessage } from "@/components/feedback";
import { json, request, type Character, type Recommendation, type Session, type Shot, type ShotSpec } from "@/lib/api";

const textarea = "mt-1.5 w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-400";
const label = "block text-xs font-medium uppercase tracking-wide text-zinc-500";

export function ShotSpecPanel({ shot, session, spec, onSpecChange, onRecommendation }: { shot: Shot; session: Session; spec: ShotSpec | null; onSpecChange: (value: ShotSpec) => void; onRecommendation: (value: Recommendation | null) => void }) {
  const [characters, setCharacters] = useState<Character[]>([]);
  const [decisions, setDecisions] = useState<Recommendation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const canEdit = ["draft", "ready", "failed", "rejected"].includes(shot.status);

  useEffect(() => {
    if (!spec) return;
    Promise.all([
      request<Character[]>(`/series/${spec.series_id}/characters`, session),
      request<Recommendation[]>(`/shots/${shot.id}/recommendations`, session),
    ]).then(([people, history]) => { setCharacters(people); setDecisions(history); onRecommendation(history.find(item => item.spec_version === spec.version) ?? null); }).catch(cause => setError((cause as Error).message));
  }, [spec?.series_id, spec?.version, shot.id, session]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(null); setNotice(null);
    const data = new FormData(event.currentTarget);
    try {
      const value = await request<ShotSpec>(`/shots/${shot.id}/spec`, session, json("PUT", {
        expected_version: spec?.version ?? 0,
        character_ids: data.getAll("character_ids"), location: String(data.get("location") ?? ""),
        action: String(data.get("action") ?? ""), dialogue: String(data.get("dialogue") ?? ""),
        continuity_notes: String(data.get("continuity_notes") ?? ""),
      }));
      onSpecChange(value); setNotice(`Shot spec v${value.version} saved.`);
    } catch (cause) { setError((cause as Error).message); } finally { setBusy(false); }
  }

  async function recommend() {
    setBusy(true); setError(null); setNotice(null);
    try { const value = await request<Recommendation>(`/shots/${shot.id}/recommendation`, session, json("POST", {})); setDecisions(current => [value, ...current]); onRecommendation(value); setNotice("Recommendation saved and applied below."); }
    catch (cause) { setError((cause as Error).message); } finally { setBusy(false); }
  }

  const latest = decisions.find(item => item.spec_version === spec?.version);
  return <Card><CardHeader><h2 className="font-semibold">Structured shot spec</h2><p className="text-sm text-zinc-500">Add the action, dialogue, and character continuity used to compile generation prompts.</p></CardHeader><CardContent className="space-y-5"><ErrorMessage message={error} />{notice && <p role="status" className="text-sm text-emerald-400">{notice}</p>}
    {spec && <><div className="flex flex-wrap gap-3 text-xs text-zinc-400"><span>{spec.saved ? `Saved version ${spec.version}` : "Unsaved"}</span><span>{spec.duration_seconds}s</span><span>{spec.motion_complexity} motion</span><span>{spec.quality_requirement} quality</span></div>
      <form key={`${shot.id}-${spec.version}`} onSubmit={save} className="space-y-4"><fieldset disabled={!canEdit} className="space-y-4"><label className={label}>Location<input name="location" defaultValue={spec.location} maxLength={160} className="mt-1.5 h-9 w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 text-sm text-zinc-100" /></label>
        <label className={label}>Action<textarea name="action" defaultValue={spec.action} rows={3} maxLength={5000} className={textarea} /></label>
        <label className={label}>Dialogue<textarea name="dialogue" defaultValue={spec.dialogue} rows={2} maxLength={5000} className={textarea} /></label>
        <label className={label}>Continuity notes<textarea name="continuity_notes" defaultValue={spec.continuity_notes} rows={2} maxLength={5000} className={textarea} /></label>
        <fieldset><legend className={label}>Characters in shot</legend>{characters.length === 0 ? <p className="mt-2 text-sm text-zinc-500">Add characters on the series page to select them here.</p> : <div className="mt-2 flex flex-wrap gap-3">{characters.map(item => <label key={item.id} className="flex items-center gap-2 text-sm text-zinc-300"><input type="checkbox" name="character_ids" value={item.id} defaultChecked={spec.character_ids.includes(item.id)} />{item.name}</label>)}</div>}</fieldset>
        {canEdit ? <Button disabled={busy}>Save spec</Button> : <p className="text-sm text-zinc-500">This spec is locked during generation and review, and after acceptance.</p>}</fieldset>
      </form>
      <div className="border-t border-zinc-800 pt-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="font-semibold">Provider recommendation</h3><p className="text-xs text-zinc-500">Demo rule, low confidence. Mock providers have no measured quality advantage.</p></div><Button type="button" variant="secondary" disabled={busy || !spec.saved} onClick={recommend}>Recommend and save</Button></div>
        {latest ? <div className="mt-3 rounded-md border border-zinc-700 p-3 text-sm"><p className="font-medium">{latest.provider} / {latest.model} · ${Number(latest.estimated_cost).toFixed(2)} simulated estimate</p><p className="mt-1 text-zinc-400">{latest.reason}</p><p className="mt-1 text-xs text-zinc-500">Spec v{latest.spec_version} · {latest.rule_version} · {latest.confidence} confidence</p></div> : <p className="mt-3 text-sm text-zinc-500">No recommendation for this spec version.</p>}
        {decisions.length > 1 && <details className="mt-3 text-sm text-zinc-400"><summary className="cursor-pointer">Past recommendations ({decisions.length})</summary><div className="mt-2 space-y-1">{decisions.map(item => <p key={item.id}>v{item.spec_version} · {item.provider} / {item.model} · ${Number(item.estimated_cost).toFixed(2)} · {new Date(item.created_at).toLocaleString()}</p>)}</div></details>}
      </div>
    </>}
  </CardContent></Card>;
}
