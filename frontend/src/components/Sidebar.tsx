"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// Primary nav: the everyday workflow. "Does this help the user decide what
// job to apply for, or help them apply faster?" - if not, it lives in
// Advanced below instead of competing with the core workflow.
const PRIMARY_NAV_ITEMS = [
  { href: "/dashboard", label: "Home", icon: "▦" },
  { href: "/applications", label: "Applications", icon: "☷" },
  { href: "/profile", label: "Profile", icon: "▤" },
  { href: "/settings", label: "Settings", icon: "⚙" },
];

// Everything here is real, working engineering (discovery runs, source
// health, company watchlist, cost/AI trace detail, the full 6-tab
// Application Workspace) - just not part of the everyday flow, so it's
// grouped separately rather than deleted or hidden entirely.
const ADVANCED_NAV_ITEMS = [
  { href: "/discover", label: "Discover", icon: "✦" },
  { href: "/companies", label: "Companies", icon: "◫" },
  { href: "/jobs", label: "All Jobs", icon: "▤" },
  { href: "/analysis", label: "Analysis", icon: "◈" },
];

function NavLink({
  href,
  label,
  icon,
  active,
}: {
  href: string;
  label: string;
  icon: string;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${
        active
          ? "bg-indigo-500/10 text-indigo-300"
          : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
      }`}
    >
      <span className="text-base leading-none">{icon}</span>
      {label}
    </Link>
  );
}

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-screen w-60 shrink-0 flex-col border-r border-zinc-800 bg-zinc-950 px-4 py-6">
      <div className="mb-8 px-2">
        <p className="text-sm font-semibold tracking-wide text-zinc-100">Job Intelligence</p>
        <p className="text-xs text-zinc-500">Find, prepare, apply.</p>
      </div>
      <nav className="flex flex-col gap-1">
        {PRIMARY_NAV_ITEMS.map((item) => (
          <NavLink key={item.href} {...item} active={pathname?.startsWith(item.href) ?? false} />
        ))}
      </nav>

      <div className="mt-8">
        <p className="mb-1 px-3 text-xs font-semibold uppercase tracking-wide text-zinc-600">
          Advanced
        </p>
        <nav className="flex flex-col gap-1">
          {ADVANCED_NAV_ITEMS.map((item) => (
            <NavLink
              key={item.href}
              {...item}
              active={pathname?.startsWith(item.href) ?? false}
            />
          ))}
        </nav>
      </div>

      <div className="mt-auto px-2 text-xs text-zinc-600">Autonomous discovery</div>
    </aside>
  );
}
