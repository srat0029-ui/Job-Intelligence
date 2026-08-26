"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: "▦" },
  { href: "/discover", label: "Discover", icon: "✦" },
  { href: "/companies", label: "Companies", icon: "◫" },
  { href: "/jobs", label: "Jobs", icon: "☷" },
  { href: "/profile", label: "Candidate Profile", icon: "▤" },
  { href: "/analysis", label: "Analysis", icon: "◈" },
  { href: "/settings", label: "Settings", icon: "⚙" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-screen w-60 shrink-0 flex-col border-r border-zinc-800 bg-zinc-950 px-4 py-6">
      <div className="mb-8 px-2">
        <p className="text-sm font-semibold tracking-wide text-zinc-100">Job Intelligence</p>
        <p className="text-xs text-zinc-500">AI job search command centre</p>
      </div>
      <nav className="flex flex-col gap-1">
        {NAV_ITEMS.map((item) => {
          const active = pathname?.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${
                active
                  ? "bg-indigo-500/10 text-indigo-300"
                  : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
              }`}
            >
              <span className="text-base leading-none">{item.icon}</span>
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto px-2 text-xs text-zinc-600">Autonomous discovery</div>
    </aside>
  );
}
