"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { RecommendationBadge } from "@/components/RecommendationBadge";
import { Card, EmptyState, ErrorBanner, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { scoreColorClass } from "@/lib/format";
import type { JobListItem, Recommendation } from "@/lib/types";

export default function AnalysisPage() {
  const [items, setItems] = useState<JobListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getPrioritizedJobs()
      .then(setItems)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100">Analysis</h1>
        <p className="mt-1 text-sm text-zinc-400">
          Every job you&apos;ve entered, ranked by fit score - highest priority first.
        </p>
      </div>

      {loading && <Spinner />}
      {error && <ErrorBanner message={error} />}

      {!loading && !error && (
        <Card>
          {items.length === 0 ? (
            <EmptyState
              title="Nothing to prioritise yet"
              subtitle="Add and analyse a few jobs to see them ranked here."
            />
          ) : (
            <div className="divide-y divide-zinc-800">
              {items.map((item, index) => (
                <Link
                  key={item.id}
                  href={`/jobs/${item.id}`}
                  className="flex items-center gap-4 py-3 transition hover:bg-zinc-800/40"
                >
                  <span className="w-6 shrink-0 text-sm text-zinc-600">{index + 1}</span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-zinc-200">{item.title}</p>
                    <p className="truncate text-xs text-zinc-500">
                      {item.company}
                      {item.location ? ` · ${item.location}` : ""}
                    </p>
                  </div>
                  {item.latest_overall_score != null ? (
                    <>
                      <span
                        className={`w-10 shrink-0 text-right text-sm font-semibold ${scoreColorClass(item.latest_overall_score)}`}
                      >
                        {item.latest_overall_score.toFixed(0)}
                      </span>
                      <div className="w-32 shrink-0">
                        <RecommendationBadge
                          recommendation={item.latest_recommendation as Recommendation}
                        />
                      </div>
                    </>
                  ) : (
                    <span className="shrink-0 text-xs text-zinc-600">Not analysed</span>
                  )}
                </Link>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
