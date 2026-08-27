import type {
  ApplicationStatus,
  AttentionItemType,
  ClaimVerificationStatus,
  CompanyPriority,
  DiscoveredJobStatus,
  DuplicateMatchStage,
  EvidenceStrength,
  EvidenceTier,
  GapStrategyCategory,
  GenerationStatus,
  JobPriority,
  QuestionType,
  Recommendation,
  ReviewVerdict,
  SourceHealthStatus,
  SourceQualityTier,
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

// Friendlier product-facing labels over the same backend ApplicationStatus
// values - a pure copy change, no schema/migration impact. "interested"
// reads as "Ready to Apply" and "applying" as "Preparing" because that's
// the mental model the simplified UI uses (see Applications page).
export const APPLICATION_STATUS_LABEL: Record<ApplicationStatus, string> = {
  interested: "Ready to Apply",
  applying: "Preparing",
  applied: "Applied",
  interview: "Interview",
  rejected: "Rejected",
  offer: "Offer",
  withdrawn: "Withdrawn",
  ignored: "Not Interested",
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

export const VERIFICATION_STATUS_LABEL: Record<ClaimVerificationStatus, string> = {
  verified_fact: "Verified fact",
  reasonable_inference: "Reasonable inference",
  unknown: "Unverified",
};

export const VERIFICATION_STATUS_CLASSES: Record<ClaimVerificationStatus, string> = {
  verified_fact: "bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/30",
  reasonable_inference: "bg-amber-500/15 text-amber-400 ring-1 ring-amber-500/30",
  unknown: "bg-rose-500/15 text-rose-400 ring-1 ring-rose-500/30",
};

export const SOURCE_QUALITY_LABEL: Record<SourceQualityTier, string> = {
  high: "High quality",
  medium: "Medium quality",
  low: "Low quality",
};

export const SOURCE_QUALITY_CLASSES: Record<SourceQualityTier, string> = {
  high: "bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/30",
  medium: "bg-sky-500/15 text-sky-400 ring-1 ring-sky-500/30",
  low: "bg-zinc-500/15 text-zinc-400 ring-1 ring-zinc-500/30",
};

export const EVIDENCE_STRENGTH_LABEL: Record<EvidenceStrength, string> = {
  strong: "Strong",
  partial: "Partial / transferable",
  weak: "Weak",
  gap: "Gap",
};

export const EVIDENCE_STRENGTH_CLASSES: Record<EvidenceStrength, string> = {
  strong: "bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/30",
  partial: "bg-sky-500/15 text-sky-400 ring-1 ring-sky-500/30",
  weak: "bg-amber-500/15 text-amber-400 ring-1 ring-amber-500/30",
  gap: "bg-rose-500/15 text-rose-400 ring-1 ring-rose-500/30",
};

export const GAP_STRATEGY_LABEL: Record<GapStrategyCategory, string> = {
  acknowledge_honestly: "Acknowledge honestly",
  demonstrate_transferable: "Demonstrate transferable skill",
  provide_project_evidence: "Provide project evidence",
  show_rapid_learning: "Show rapid-learning evidence",
  do_not_address: "Do not address unless asked",
};

export const GENERATION_STATUS_LABEL: Record<GenerationStatus, string> = {
  draft: "Draft",
  reviewed: "Reviewed",
  needs_review: "Needs review",
  archived: "Archived (superseded)",
};

export const REVIEW_VERDICT_LABEL: Record<ReviewVerdict, string> = {
  pass: "Pass",
  pass_with_warnings: "Pass with warnings",
  fail: "Fail - needs review",
};

export const REVIEW_VERDICT_CLASSES: Record<ReviewVerdict, string> = {
  pass: "bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/30",
  pass_with_warnings: "bg-amber-500/15 text-amber-400 ring-1 ring-amber-500/30",
  fail: "bg-rose-500/15 text-rose-400 ring-1 ring-rose-500/30",
};

export const QUESTION_TYPE_LABEL: Record<QuestionType, string> = {
  motivation: "Motivation",
  company_motivation: "Company motivation",
  technical_experience: "Technical experience",
  behavioural: "Behavioural",
  values: "Values",
  teamwork: "Teamwork",
  leadership: "Leadership",
  problem_solving: "Problem solving",
  learning: "Learning",
  project_experience: "Project experience",
  work_rights: "Work rights",
  salary: "Salary",
  general_background: "General background",
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

/** "Last checked: 12 minutes ago" style text (Part 11 of the
 * simplification brief) - deliberately never says "Discovery Run". */
export function formatRelativeTime(iso?: string | null): string {
  if (!iso) return "never";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "never";
  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
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
