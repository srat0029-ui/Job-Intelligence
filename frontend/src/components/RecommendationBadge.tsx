import {
  PRIORITY_CLASSES,
  PRIORITY_LABEL,
  RECOMMENDATION_CLASSES,
  RECOMMENDATION_LABEL,
  TIER_CLASSES,
  TIER_LABEL,
} from "@/lib/format";
import type { EvidenceTier, JobPriority, Recommendation } from "@/lib/types";
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
