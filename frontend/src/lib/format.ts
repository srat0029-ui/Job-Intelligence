import type {
  ApplicationStatus,
  AttentionItemType,
  CompanyPriority,
  DiscoveredJobStatus,
  DuplicateMatchStage,
  EvidenceTier,
  JobPriority,
  Recommendation,
  SourceHealthStatus,
} from "./types";

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

export const PRIORITY_LABEL: Record<JobPriority, string> = {
  apply_asap: "Apply ASAP",
  strong_apply: "Strong Apply",
  apply: "Apply",
  stretch: "Stretch",
  low_priority: "Low Priority",
};

export const PRIORITY_CLASSES: Record<JobPriority, string> = {
  apply_asap: "bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/40 font-semibold",
  strong_apply: "bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/30",
  apply: "bg-sky-500/15 text-sky-400 ring-1 ring-sky-500/30",
  stretch: "bg-amber-500/15 text-amber-400 ring-1 ring-amber-500/30",
  low_priority: "bg-zinc-500/15 text-zinc-400 ring-1 ring-zinc-500/30",
};

export const APPLICATION_STATUS_LABEL: Record<ApplicationStatus, string> = {
  interested: "Interested",
  applying: "Applying",
  applied: "Applied",
  interview: "Interview",
  rejected: "Rejected",
  offer: "Offer",
  withdrawn: "Withdrawn",
  ignored: "Ignored",
};

export const APPLICATION_STATUS_OPTIONS: ApplicationStatus[] = [
  "interested",
  "applying",
  "applied",
  "interview",
  "offer",
  "rejected",
  "withdrawn",
  "ignored",
];

export const DISCOVERED_STATUS_LABEL: Record<DiscoveredJobStatus, string> = {
  discovered: "Discovered",
  duplicate: "Duplicate",
  prefilter_rejected: "Filtered out",
  awaiting_analysis: "Awaiting analysis",
  analysing: "Analysing",
  analysed: "Analysed",
  analysis_failed: "Analysis failed",
  archived: "Archived",
};

export const COMPANY_PRIORITY_LABEL: Record<CompanyPriority, string> = {
  high: "High priority",
  normal: "Normal priority",
  low: "Low priority",
};

export const COMPANY_PRIORITY_CLASSES: Record<CompanyPriority, string> = {
  high: "bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/30",
  normal: "bg-zinc-500/15 text-zinc-400 ring-1 ring-zinc-500/30",
  low: "bg-zinc-700/30 text-zinc-500 ring-1 ring-zinc-700/40",
};

export const SOURCE_HEALTH_LABEL: Record<SourceHealthStatus, string> = {
  healthy: "Healthy",
  degraded: "Degraded",
  error: "Error",
  unknown: "Unknown",
};

export const SOURCE_HEALTH_CLASSES: Record<SourceHealthStatus, string> = {
  healthy: "bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/30",
  degraded: "bg-amber-500/15 text-amber-400 ring-1 ring-amber-500/30",
  error: "bg-rose-500/15 text-rose-400 ring-1 ring-rose-500/30",
  unknown: "bg-zinc-500/15 text-zinc-400 ring-1 ring-zinc-500/30",
};

export const ATTENTION_TYPE_LABEL: Record<AttentionItemType, string> = {
  high_priority_job: "High-priority job",
  watchlist_company_posting: "Watchlisted company posting",
  analysis_failures: "Analysis failures",
  source_unhealthy: "Source unhealthy",
};

export const DUPLICATE_MATCH_STAGE_LABEL: Record<DuplicateMatchStage, string> = {
  exact_id: "Exact ID/URL match",
  canonical_url: "Canonical URL match",
  deterministic_fingerprint: "Deterministic fingerprint match",
  fuzzy: "Fuzzy match",
  original: "First sighting",
};

export function formatDateTime(iso?: string | null): string {
  if (!iso) return "-";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  try {
    return date.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

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
