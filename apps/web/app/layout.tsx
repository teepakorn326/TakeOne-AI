import Link from "next/link";
import "./globals.css";

export const metadata = { title: "TakeOne AI", description: "Production economics for AI video studios" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><div className="min-h-screen">
    <header className="border-b border-zinc-800 bg-[#15171b]"><div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
      <Link href="/series" className="shrink-0 whitespace-nowrap text-lg font-semibold tracking-tight">TAKEONE <span className="text-zinc-500">AI</span></Link>
      <nav className="flex flex-wrap gap-4 text-sm text-zinc-400 md:gap-6"><Link href="/dashboard" className="hover:text-white">Dashboard</Link><Link href="/series" className="hover:text-white">Production</Link><Link href="/review" className="hover:text-white">Review</Link><Link href="/analytics" className="hover:text-white">Analytics</Link><Link href="/settings/providers" className="hover:text-white">Providers</Link></nav>
    </div></header>
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">{children}</main>
  </div></body></html>;
}
