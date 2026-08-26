"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { RecommendationBadge } from "@/components/RecommendationBadge";
import { Card, EmptyState, ErrorBanner, SectionHeading, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { scoreColorClass } from "@/lib/format";
import type { DashboardStats, JobListItem, Recommendation } from "@/lib/types";

function StatTile({ label, value }: { label: string; value: string | number }) {
  return (
    <Card>
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-2 text-3xl font-semibold text-zinc-100">{value}</p>
    </Card>
  );
}

function JobRow({ item }: { item: JobListItem }) {
  return (
    <Link
      href={`/jobs/${item.id}`}
      className="flex items-center justify-between gap-4 rounded-lg px-3 py-2.5 transition hover:bg-zinc-800/60"
    >
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-zinc-200">{item.title}</p>
        <p className="truncate text-xs text-zinc-500">
          {item.company}
          {item.location ? ` · ${item.location}` : ""}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-3">
        {item.latest_overall_score != null && (
          <span className={`text-sm font-semibold ${scoreColorClass(item.latest_overall_score)}`}>
            {item.latest_overall_score.toFixed(0)}
          </span>
        )}
        {item.latest_recommendation && (
          <RecommendationBadge recommendation={item.latest_recommendation as Recommendation} />
        )}
      </div>
    </Link>
  );
}

const BUCKET_ORDER = ["80-100", "60-79", "40-59", "20-39", "0-19"];

function ScoreDistribution({ distribution }: { distribution: Record<string, number> }) {
  const max = Math.max(1, ...Object.values(distribution));
  return (
    <div className="space-y-2.5">
      {BUCKET_ORDER.map((bucket) => {
        const count = distribution[bucket] ?? 0;
        return (
          <div key={bucket} className="flex items-center gap-3">
            <span className="w-14 shrink-0 text-xs text-zinc-500">{bucket}</span>
            <div className="h-3 flex-1 overflow-hidden rounded-full bg-zinc-800">
              <div
                className="h-full rounded-full bg-indigo-500"
                style={{ width: `${(count / max) * 100}%` }}
              />
            </div>
            <span className="w-6 shrink-0 text-right text-xs text-zinc-400">{count}</span>
          </div>
        );
      })}
    </div>
  );
}

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getDashboard()
      .then(setStats)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spinner />;
  if (error) return <ErrorBanner message={error} />;
  if (!stats) return null;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100">Dashboard</h1>
        <p className="mt-1 text-sm text-zinc-400">
          Your job search at a glance.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-2">
        <StatTile label="Jobs tracked" value={stats.total_jobs} />
        <StatTile label="Analyses run" value={stats.total_analyses} />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <SectionHeading title="Strongest opportunities" subtitle="Highest current fit score" />
          {stats.strongest_opportunities.length === 0 ? (
            <EmptyState
              title="No analyses yet"
              subtitle="Add a job and run an analysis to see it here."
            />
          ) : (
            <div className="space-y-1">
              {stats.strongest_opportunities.map((item) => (
                <JobRow key={item.id} item={item} />
              ))}
            </div>
          )}
        </Card>

        <Card>
          <SectionHeading title="Recent analyses" subtitle="Most recently analysed jobs" />
          {stats.recent_analyses.length === 0 ? (
            <EmptyState title="Nothing analysed yet" />
          ) : (
            <div className="space-y-1">
              {stats.recent_analyses.map((item) => (
                <JobRow key={item.id} item={item} />
              ))}
            </div>
          )}
        </Card>
      </div>

      <Card>
        <SectionHeading title="Score distribution" subtitle="Across all analysed jobs" />
        <ScoreDistribution distribution={stats.score_distribution} />
      </Card>
    </div>
  );
}
