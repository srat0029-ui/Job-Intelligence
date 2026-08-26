"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { RecommendationBadge, SourceHealthBadge } from "@/components/RecommendationBadge";
import { Card, EmptyState, ErrorBanner, SectionHeading, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTime, scoreColorClass } from "@/lib/format";
import type { DashboardStats, DiscoveryDashboardStats, JobListItem, Recommendation } from "@/lib/types";

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

function DiscoverySummary({ stats }: { stats: DiscoveryDashboardStats }) {
  return (
    <Card>
      <SectionHeading
        title="Discovery"
        subtitle="What automated discovery has found and whether it's running on schedule"
        action={
          <Link href="/discover" className="text-xs text-indigo-400 hover:underline">
            Go to Discover ↗
          </Link>
        }
      />
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatTile label="New jobs today" value={stats.new_jobs_today} />
        <StatTile label="High priority, unreviewed" value={stats.high_priority_unreviewed} />
        <StatTile label="Unread notifications" value={stats.unread_attention_count} />
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-5 shadow-sm">
          <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">Scheduler</p>
          <p className="mt-2 text-sm font-medium text-zinc-200">
            {stats.auto_discovery_enabled ? "Enabled" : "Disabled"}
          </p>
          <p className="mt-1 text-xs text-zinc-500">
            Next run: {formatDateTime(stats.next_scheduled_run_at)}
          </p>
        </div>
      </div>

      {stats.source_health.length > 0 && (
        <div className="mt-5 border-t border-zinc-800 pt-4">
          <p className="mb-2 text-xs font-medium text-zinc-500">Source health</p>
          <div className="flex flex-wrap gap-2">
            {stats.source_health.map((h) => (
              <div
                key={h.source_key}
                className="flex items-center gap-2 rounded-lg border border-zinc-800 px-3 py-1.5"
              >
                <span className="text-xs font-medium text-zinc-300">{h.source_key}</span>
                <SourceHealthBadge status={h.status} />
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [discoveryStats, setDiscoveryStats] = useState<DiscoveryDashboardStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.getDashboard(), api.getDiscoveryDashboard()])
      .then(([s, d]) => {
        setStats(s);
        setDiscoveryStats(d);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
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

      {discoveryStats && <DiscoverySummary stats={discoveryStats} />}

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
