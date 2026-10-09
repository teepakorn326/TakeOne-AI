"use client";

import { FormEvent, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ErrorMessage } from "@/components/feedback";
import { json, request, type Character, type CharacterState, type Session } from "@/lib/api";

const field = "h-9 w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 text-sm text-zinc-100";
const label = "block space-y-1 text-xs font-medium uppercase tracking-wide text-zinc-500";

function characterPayload(form: HTMLFormElement) {
  const data = new FormData(form);
  return { name: String(data.get("name") ?? ""), description: String(data.get("description") ?? ""), visual_reference_url: String(data.get("reference") ?? ""), notes: String(data.get("notes") ?? "") };
}

function statePayload(form: HTMLFormElement) {
  const data = new FormData(form);
  return { episode_start: Number(data.get("start")), episode_end: Number(data.get("end")), hairstyle: String(data.get("hair") ?? ""), wardrobe: String(data.get("wardrobe") ?? ""), injury_state: String(data.get("injury") ?? ""), props: String(data.get("props") ?? ""), notes: String(data.get("notes") ?? "") };
}

function CharacterEditor({ character, session, onDelete, onUpdate }: { character: Character; session: Session; onDelete: (id: string) => void; onUpdate: (item: Character) => void }) {
  const [states, setStates] = useState<CharacterState[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { request<CharacterState[]>(`/characters/${character.id}/states`, session).then(setStates).catch(e => setError(e.message)); }, [character.id, session]);

  async function update(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(null);
    try { onUpdate(await request<Character>(`/characters/${character.id}`, session, json("PATCH", characterPayload(event.currentTarget)))); }
    catch (cause) { setError((cause as Error).message); } finally { setBusy(false); }
  }

  async function addState(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(null);
    const form = event.currentTarget;
    try { const value = await request<CharacterState>(`/characters/${character.id}/states`, session, json("POST", statePayload(form))); setStates(current => [...current, value].sort((a, b) => a.episode_start - b.episode_start)); form.reset(); }
    catch (cause) { setError((cause as Error).message); } finally { setBusy(false); }
  }

  async function editState(event: FormEvent<HTMLFormElement>, stateId: string) {
    event.preventDefault(); setBusy(true); setError(null);
    try { const value = await request<CharacterState>(`/character-states/${stateId}`, session, json("PATCH", statePayload(event.currentTarget))); setStates(current => current.map(item => item.id === stateId ? value : item).sort((a, b) => a.episode_start - b.episode_start)); }
    catch (cause) { setError((cause as Error).message); } finally { setBusy(false); }
  }

  async function removeState(stateId: string) {
    setBusy(true); setError(null);
    try { await request(`/character-states/${stateId}`, session, { method: "DELETE" }); setStates(current => current.filter(item => item.id !== stateId)); }
    catch (cause) { setError((cause as Error).message); } finally { setBusy(false); }
  }

  async function removeCharacter() {
    setBusy(true); setError(null);
    try { await request(`/characters/${character.id}`, session, { method: "DELETE" }); onDelete(character.id); }
    catch (cause) { setError((cause as Error).message); } finally { setBusy(false); }
  }

  return <Card><CardHeader><h3 className="font-semibold">{character.name}</h3><p className="text-sm text-zinc-500">Identity and continuity by episode range.</p></CardHeader><CardContent className="space-y-5">
    <ErrorMessage message={error} />
    <form onSubmit={update} className="grid gap-3 sm:grid-cols-2"><label className={label}>Name<Input name="name" defaultValue={character.name} required maxLength={160} /></label><label className={label}>Visual reference URL<Input name="reference" defaultValue={character.visual_reference_url} maxLength={2000} /></label><label className={label}>Description<Input name="description" defaultValue={character.description} maxLength={5000} /></label><label className={label}>Notes<Input name="notes" defaultValue={character.notes} maxLength={5000} /></label><div className="flex gap-2 sm:col-span-2"><Button disabled={busy}>Save character</Button><Button type="button" variant="secondary" disabled={busy} onClick={removeCharacter}>Delete character</Button></div></form>
    <div className="border-t border-zinc-800 pt-4"><h4 className="mb-3 text-sm font-semibold">Episode states</h4>{states.length === 0 && <p className="mb-3 text-sm text-zinc-500">No state defined. The character identity will still appear in prompts.</p>}
      <div className="space-y-3">{states.map(state => <form key={state.id} onSubmit={event => editState(event, state.id)} className="grid gap-2 rounded-md border border-zinc-800 p-3 sm:grid-cols-4"><Input name="start" type="number" min="1" defaultValue={state.episode_start} aria-label="Start episode" required /><Input name="end" type="number" min="1" defaultValue={state.episode_end} aria-label="End episode" required /><Input name="hair" defaultValue={state.hairstyle} placeholder="Hair" /><Input name="wardrobe" defaultValue={state.wardrobe} placeholder="Wardrobe" /><Input name="injury" defaultValue={state.injury_state} placeholder="Injury" /><Input name="props" defaultValue={state.props} placeholder="Props" /><Input name="notes" defaultValue={state.notes} placeholder="State notes" /><div className="flex gap-2"><Button size="sm" disabled={busy}>Save</Button><Button type="button" size="sm" variant="secondary" disabled={busy} onClick={() => removeState(state.id)}>Delete</Button></div></form>)}</div>
      <form onSubmit={addState} className="mt-4 grid gap-2 rounded-md border border-zinc-800 p-3 sm:grid-cols-4"><Input name="start" type="number" min="1" placeholder="From episode" required /><Input name="end" type="number" min="1" placeholder="Through episode" required /><Input name="hair" placeholder="Hair" /><Input name="wardrobe" placeholder="Wardrobe" /><Input name="injury" placeholder="Injury" /><Input name="props" placeholder="Props" /><Input name="notes" placeholder="State notes" /><Button size="sm" disabled={busy}>Add state</Button></form>
    </div>
  </CardContent></Card>;
}

export function CharacterPanel({ seriesId, session }: { seriesId: string; session: Session }) {
  const [characters, setCharacters] = useState<Character[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { request<Character[]>(`/series/${seriesId}/characters`, session).then(setCharacters).catch(e => setError(e.message)); }, [seriesId, session]);
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(null);
    const form = event.currentTarget;
    try { const value = await request<Character>(`/series/${seriesId}/characters`, session, json("POST", characterPayload(form))); setCharacters(current => [...current, value].sort((a, b) => a.name.localeCompare(b.name))); form.reset(); }
    catch (cause) { setError((cause as Error).message); } finally { setBusy(false); }
  }
  return <section className="space-y-4"><div><h2 className="text-xl font-semibold">Characters</h2><p className="text-sm text-zinc-500">Keep each character&apos;s look consistent across shots.</p></div><ErrorMessage message={error} />
    <Card><CardHeader><h3 className="font-semibold">Add character</h3></CardHeader><CardContent><form onSubmit={create} className="grid gap-3 sm:grid-cols-2"><Input name="name" placeholder="Name" required maxLength={160} /><Input name="reference" placeholder="Visual reference URL (optional)" maxLength={2000} /><Input name="description" placeholder="Appearance and identity" maxLength={5000} /><Input name="notes" placeholder="Continuity notes" maxLength={5000} /><Button disabled={busy}>Add character</Button></form></CardContent></Card>
    <div className="grid gap-4">{characters.map(character => <CharacterEditor key={character.id} character={character} session={session} onDelete={characterId => setCharacters(current => current.filter(item => item.id !== characterId))} onUpdate={value => setCharacters(current => current.map(item => item.id === value.id ? value : item))} />)}</div>
  </section>;
}
