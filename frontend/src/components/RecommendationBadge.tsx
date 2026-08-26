import {
  COMPANY_PRIORITY_CLASSES,
  COMPANY_PRIORITY_LABEL,
  EVIDENCE_STRENGTH_CLASSES,
  EVIDENCE_STRENGTH_LABEL,
  PRIORITY_CLASSES,
  PRIORITY_LABEL,
  RECOMMENDATION_CLASSES,
  RECOMMENDATION_LABEL,
  REVIEW_VERDICT_CLASSES,
  REVIEW_VERDICT_LABEL,
  SOURCE_HEALTH_CLASSES,
  SOURCE_HEALTH_LABEL,
  SOURCE_QUALITY_CLASSES,
  SOURCE_QUALITY_LABEL,
  TIER_CLASSES,
  TIER_LABEL,
  VERIFICATION_STATUS_CLASSES,
  VERIFICATION_STATUS_LABEL,
} from "@/lib/format";
import type {
  ClaimVerificationStatus,
  CompanyPriority,
  EvidenceStrength,
  EvidenceTier,
  JobPriority,
  Recommendation,
  ReviewVerdict,
  SourceHealthStatus,
  SourceQualityTier,
} from "@/lib/types";
import { Pill } from "./ui";

export function RecommendationBadge({ recommendation }: { recommendation: Recommendation }) {
  return (
    <Pill className={RECOMMENDATION_CLASSES[recommendation]}>
      {RECOMMENDATION_LABEL[recommendation]}
    </Pill>
  );
}

export function PriorityBadge({ priority }: { priority: JobPriority }) {
  return <Pill className={PRIORITY_CLASSES[priority]}>{PRIORITY_LABEL[priority]}</Pill>;
}

export function TierBadge({ tier }: { tier: EvidenceTier }) {
  return <Pill className={TIER_CLASSES[tier]}>{TIER_LABEL[tier]}</Pill>;
}

export function CompanyPriorityBadge({ priority }: { priority: CompanyPriority }) {
  return (
    <Pill className={COMPANY_PRIORITY_CLASSES[priority]}>{COMPANY_PRIORITY_LABEL[priority]}</Pill>
  );
}

export function SourceHealthBadge({ status }: { status: SourceHealthStatus }) {
  return <Pill className={SOURCE_HEALTH_CLASSES[status]}>{SOURCE_HEALTH_LABEL[status]}</Pill>;
}

export function VerificationStatusBadge({ status }: { status: ClaimVerificationStatus }) {
  return (
    <Pill className={VERIFICATION_STATUS_CLASSES[status]}>{VERIFICATION_STATUS_LABEL[status]}</Pill>
  );
}

export function EvidenceStrengthBadge({ strength }: { strength: EvidenceStrength }) {
  return (
    <Pill className={EVIDENCE_STRENGTH_CLASSES[strength]}>{EVIDENCE_STRENGTH_LABEL[strength]}</Pill>
  );
}

export function ReviewVerdictBadge({ verdict }: { verdict: ReviewVerdict }) {
  return <Pill className={REVIEW_VERDICT_CLASSES[verdict]}>{REVIEW_VERDICT_LABEL[verdict]}</Pill>;
}

export function SourceQualityBadge({ tier }: { tier: SourceQualityTier }) {
  return <Pill className={SOURCE_QUALITY_CLASSES[tier]}>{SOURCE_QUALITY_LABEL[tier]}</Pill>;
}
