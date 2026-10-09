"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorMessage, Status } from "@/components/feedback";
import { json, request, type Series } from "@/lib/api";
import { useSession } from "@/lib/session";

export default function SeriesPage() {
  const { session, save, clear } = useSession();
  const [items, setItems] = useState<Series[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (session) request<Series[]>("/series", session).then(setItems).catch(e => setError(e.message)); }, [session]);

  async function bootstrap(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(null);
    const form = new FormData(event.currentTarget);
    try {
      const result = await request<{ workspace: { id: string; name: string }; owner_id: string }>("/workspaces", null, json("POST", {
        name: form.get("workspace"), owner_name: form.get("name"), owner_email: form.get("email"),
      }));
      save({ workspaceId: result.workspace.id, workspaceName: result.workspace.name, userId: result.owner_id });
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  async function createSeries(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!session) return; setBusy(true); setError(null);
    const form = event.currentTarget; const data = new FormData(form);
    try {
      const item = await request<Series>("/series", session, json("POST", { title: data.get("title"), genre: data.get("genre"), description: data.get("description") }));
      setItems(current => [item, ...current]); form.reset();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  if (session === undefined) return <p className="text-zinc-400">Loading workspace…</p>;
  if (session === null) return <div className="mx-auto max-w-xl space-y-6">
    <div><p className="mb-2 text-xs font-semibold uppercase tracking-widest text-zinc-500">Local setup</p><h1 className="text-3xl font-semibold">Create your studio workspace</h1><p className="mt-2 text-zinc-400">A local development identity lets you start planning shots.</p></div>
    <Card><CardContent><form onSubmit={bootstrap} className="space-y-4"><Input name="workspace" placeholder="Studio name" required maxLength={160} /><Input name="name" placeholder="Your name" required maxLength={160} /><Input name="email" placeholder="Email" type="email" required /><ErrorMessage message={error} /><Button disabled={busy}>Create workspace</Button></form></CardContent></Card>
  </div>;

  return <div className="space-y-7">
    <div className="flex flex-wrap items-end justify-between gap-3"><div><p className="mb-1 text-xs font-semibold uppercase tracking-widest text-zinc-500">{session.workspaceName}</p><h1 className="text-3xl font-semibold">Production</h1><p className="mt-1 text-sm text-zinc-400">Organise each title into episodes, scenes, and shots.</p></div><div className="flex items-center gap-3"><Status value="Phase 5 · Shot intelligence" /><Button variant="ghost" size="sm" onClick={() => { clear(); setError(null); setItems([]); }}>Switch workspace</Button></div></div>
    <ErrorMessage message={error} />
    <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
      <Card><CardHeader><h2 className="font-semibold">Series <span className="ml-2 text-sm font-normal text-zinc-500">{items.length}</span></h2></CardHeader><CardContent className="space-y-2">{items.length === 0 ? <EmptyState>No series yet. Create your first title.</EmptyState> : items.map(item => <Link key={item.id} href={`/series/${item.id}`} className="flex items-center justify-between rounded-md border border-zinc-800 px-4 py-3 hover:border-zinc-600"><div><div className="font-medium">{item.title}</div><div className="text-xs text-zinc-500">{item.genre || "Uncategorised"}</div></div><Status value={item.status} /></Link>)}</CardContent></Card>
      <Card><CardHeader><h2 className="font-semibold">New series</h2></CardHeader><CardContent><form onSubmit={createSeries} className="space-y-3"><Input name="title" placeholder="Title" required maxLength={200} /><Input name="genre" placeholder="Genre" maxLength={80} /><textarea name="description" placeholder="Description" rows={4} className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm outline-none focus:border-zinc-400" /><Button disabled={busy}>Create series</Button></form></CardContent></Card>
    </div>
  </div>;
}
