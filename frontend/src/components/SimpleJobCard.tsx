"use client";

import { PriorityBadge, RecommendationBadge } from "@/components/RecommendationBadge";
import { Card, PrimaryButton, SecondaryButton } from "@/components/ui";
import { formatDate, scoreColorClass } from "@/lib/format";
import type { OpportunityItem } from "@/lib/types";

function formatSalary(item: OpportunityItem): string | null {
  if (item.salary_min == null && item.salary_max == null) return null;
  const currency = item.currency ?? "AUD";
  if (item.salary_min != null && item.salary_max != null) {
    return `${currency} ${item.salary_min.toLocaleString()} - ${item.salary_max.toLocaleString()}`;
  }
  const amount = item.salary_min ?? item.salary_max;
  return `${currency} ${amount?.toLocaleString()}`;
}

/** The heart of the simplified product experience (Part 8 of the
 * simplification brief): everything a person needs to decide whether to
 * open a job, with no pipeline/engineering metadata in sight. */
export function SimpleJobCard({
  item,
  onPrepare,
  onNotInterested,
  preparing,
}: {
  item: OpportunityItem;
  onPrepare: () => void;
  onNotInterested: () => void;
  preparing: boolean;
}) {
  const salary = formatSalary(item);
  const reasons = item.why_summary.length > 0 ? item.why_summary : item.strong_matches;

  return (
    <Card className="transition hover:border-zinc-700">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-4">
          {item.overall_score != null && (
            <div className={`text-3xl font-bold ${scoreColorClass(item.overall_score)}`}>
              {item.overall_score.toFixed(0)}
            </div>
          )}
          <div>
            <p className="text-base font-semibold text-zinc-100">{item.title}</p>
            <p className="text-sm text-zinc-400">
              {item.company}
              {item.location ? ` · ${item.location}` : ""}
            </p>
            <p className="mt-1 flex flex-wrap gap-x-3 text-xs text-zinc-500">
              {salary && <span>{salary}</span>}
              <span>Posted {formatDate(item.published_at)}</span>
              {item.source && <span className="capitalize">via {item.source}</span>}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          {item.priority && <PriorityBadge priority={item.priority} />}
          {item.recommendation && <RecommendationBadge recommendation={item.recommendation} />}
        </div>
      </div>

      {reasons.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-medium text-zinc-500">Why it suits you</p>
          <ul className="mt-1 list-inside list-disc space-y-0.5 text-sm text-zinc-300">
            {reasons.slice(0, 5).map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
        </div>
      )}

      {item.main_gap && (
        <p className="mt-2 text-sm text-amber-400">Gap: {item.main_gap}</p>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <PrimaryButton onClick={onPrepare} disabled={preparing}>
          {preparing ? "Preparing..." : "Prepare Application"}
        </PrimaryButton>
        {item.source_url && (
          <a
            href={item.source_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center justify-center rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-2 text-sm font-medium text-zinc-200 transition hover:bg-zinc-800"
          >
            View Original Job ↗
          </a>
        )}
        <SecondaryButton onClick={onNotInterested} className="ml-auto border-transparent bg-transparent text-zinc-500 hover:bg-zinc-900 hover:text-zinc-300">
          Not Interested
        </SecondaryButton>
      </div>
    </Card>
  );
}
