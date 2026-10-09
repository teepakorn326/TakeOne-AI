import * as React from "react";
import { cn } from "@/lib/utils";
export function Card({ className, ...props }: React.ComponentProps<"div">) { return <div className={cn("rounded-lg border border-zinc-800 bg-[#191b20]", className)} {...props} />; }
export function CardHeader({ className, ...props }: React.ComponentProps<"div">) { return <div className={cn("border-b border-zinc-800 px-5 py-4", className)} {...props} />; }
export function CardContent({ className, ...props }: React.ComponentProps<"div">) { return <div className={cn("p-5", className)} {...props} />; }
