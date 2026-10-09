import * as React from "react";
import { cn } from "@/lib/utils";
export function Input({ className, ...props }: React.ComponentProps<"input">) {
  return <input className={cn("h-9 w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 text-sm outline-none placeholder:text-zinc-500 focus:border-zinc-400", className)} {...props} />;
}

