import type { EvidenceTier, Recommendation } from "./types";

export const RECOMMENDATION_LABEL: Record<Recommendation, string> = {
  strong_apply: "Strong Apply",
  apply: "Apply",
  stretch: "Stretch",
  low_priority: "Low Priority",
};

export const RECOMMENDATION_CLASSES: Record<Recommendation, string> = {
  strong_apply: "bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/30",
  apply: "bg-sky-500/15 text-sky-400 ring-1 ring-sky-500/30",
  stretch: "bg-amber-500/15 text-amber-400 ring-1 ring-amber-500/30",
  low_priority: "bg-zinc-500/15 text-zinc-400 ring-1 ring-zinc-500/30",
};

export const TIER_LABEL: Record<EvidenceTier, string> = {
  explicit: "Explicit match",
  transferable: "Transferable",
  weak_inference: "Weak inference",
  no_evidence: "No evidence",
};

export const TIER_CLASSES: Record<EvidenceTier, string> = {
  explicit: "bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/30",
  transferable: "bg-sky-500/15 text-sky-400 ring-1 ring-sky-500/30",
  weak_inference: "bg-amber-500/15 text-amber-400 ring-1 ring-amber-500/30",
  no_evidence: "bg-rose-500/15 text-rose-400 ring-1 ring-rose-500/30",
};

export function scoreColorClass(score: number): string {
  if (score >= 80) return "text-emerald-400";
  if (score >= 65) return "text-sky-400";
  if (score >= 45) return "text-amber-400";
  return "text-rose-400";
}

export function scoreBarColorClass(score: number): string {
  if (score >= 80) return "bg-emerald-500";
  if (score >= 65) return "bg-sky-500";
  if (score >= 45) return "bg-amber-500";
  return "bg-rose-500";
}

export function formatDate(iso?: string | null): string {
  if (!iso) return "-";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  try {
    return date.toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

export function categoryLabel(category: string): string {
  return category
    .split("_")
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");
}
