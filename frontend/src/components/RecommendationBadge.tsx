import {
  COMPANY_PRIORITY_CLASSES,
  COMPANY_PRIORITY_LABEL,
  PRIORITY_CLASSES,
  PRIORITY_LABEL,
  RECOMMENDATION_CLASSES,
  RECOMMENDATION_LABEL,
  SOURCE_HEALTH_CLASSES,
  SOURCE_HEALTH_LABEL,
  TIER_CLASSES,
  TIER_LABEL,
} from "@/lib/format";
import type {
  CompanyPriority,
  EvidenceTier,
  JobPriority,
  Recommendation,
  SourceHealthStatus,
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
