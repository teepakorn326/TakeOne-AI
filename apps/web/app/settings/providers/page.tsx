"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { ErrorMessage, SessionNeeded, Status } from "@/components/feedback";
import { request, type Provider } from "@/lib/api";
import { useSession } from "@/lib/session";

export default function ProvidersPage() {
  const { session } = useSession();
  const [items, setItems] = useState<Provider[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (session) request<Provider[]>("/settings/providers", session).then(setItems).catch(e => setError(e.message)); }, [session]);
  if (session === undefined) return <p className="text-zinc-400">Loading…</p>;
  if (!session) return <SessionNeeded />;
  return <div className="max-w-4xl space-y-7">
    <div><p className="mb-1 text-xs font-semibold uppercase tracking-widest text-zinc-500">Settings</p><h1 className="text-3xl font-semibold">Video providers</h1><p className="mt-2 text-sm text-zinc-400">Available generation adapters and their limits.</p></div>
    <ErrorMessage message={error} />
    {items.map(item => <Card key={item.name}><CardHeader><div className="flex items-center justify-between"><h2 className="font-semibold capitalize">{item.name}</h2><Status value={item.is_mock ? "Mock · Local" : "Connected"} /></div></CardHeader><CardContent className="grid gap-4 text-sm sm:grid-cols-3"><div><p className="text-zinc-500">Models</p><p className="mt-1">{item.models.join(", ")}</p></div><div><p className="text-zinc-500">Maximum duration</p><p className="mt-1">{item.max_duration_seconds}s</p></div><div><p className="text-zinc-500">Output</p><p className="mt-1">{item.is_mock ? "Sample frame, simulated charge" : item.media_type}</p></div></CardContent></Card>)}
    <p className="text-sm text-zinc-500">Both entries are local simulations with different prices. Real provider connections are still to come.</p>
  </div>;
}
