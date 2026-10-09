import Link from "next/link";

export function ErrorMessage({ message }: { message: string | null }) {
  return message ? <p role="alert" className="rounded-md border border-red-900 bg-red-950/40 px-3 py-2 text-sm text-red-300">{message}</p> : null;
}

export function EmptyState({ children }: { children: React.ReactNode }) {
  return <div className="rounded-md border border-dashed border-zinc-700 px-4 py-8 text-center text-sm text-zinc-500">{children}</div>;
}

export function SessionNeeded() {
  return <div className="space-y-3"><h1 className="text-2xl font-semibold">Start a local workspace</h1><p className="text-zinc-400">Create your development workspace to continue.</p><Link href="/series" className="text-sm underline">Go to Production</Link></div>;
}

export function Status({ value }: { value: string }) {
  return <span className="rounded-full border border-zinc-700 bg-zinc-800 px-2 py-0.5 text-xs capitalize text-zinc-300">{value}</span>;
}

