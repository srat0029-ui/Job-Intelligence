"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { SimpleJobCard } from "@/components/SimpleJobCard";
import { Card, EmptyState, ErrorBanner, SecondaryButton, Spinner } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { formatRelativeTime } from "@/lib/format";
import type { GmailStatus, JobPriority, OpportunityItem } from "@/lib/types";

// Part 13 of the simplification brief: three simple, always-visible groups
// (never an arbitrary quota) - only "low_priority" is hidden by default.
const GROUPS: { key: string; title: string; priorities: JobPriority[] }[] = [
  { key: "best", title: "Best matches", priorities: ["apply_asap", "strong_apply"] },
  { key: "good", title: "Good matches", priorities: ["apply"] },
  { key: "maybe", title: "Maybe", priorities: ["stretch"] },
];
const DEFAULT_VISIBLE_PRIORITIES: JobPriority[] = GROUPS.flatMap((g) => g.priorities);

const PREPARING_MESSAGES = [
  "Analysing fit...",
  "Researching the company...",
  "Tailoring your application...",
];

// How stale "last checked" needs to be before Home triggers a background
// sync itself on load (Part 11) - never blocks rendering the existing feed.
const STALE_SYNC_MINUTES = 30;

export default function HomePage() {
  const router = useRouter();
  const [opportunities, setOpportunities] = useState<OpportunityItem[]>([]);
  const [gmailStatus, setGmailStatus] = useState<GmailStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [preparingJobId, setPreparingJobId] = useState<string | null>(null);
  const [preparingMessageIndex, setPreparingMessageIndex] = useState(0);
  const [refreshing, setRefreshing] = useState(false);

  const loadFeed = useCallback(async () => {
    const page = await api.listOpportunities({
      sortBy: "score",
      analysedOnly: true,
      pageSize: 100,
    });
    // Jobs already underway (preparing/applied/interview/...) belong on
    // the Applications page, not cluttering the "what's new" home feed.
    setOpportunities(
      page.items.filter((o) => !o.application_status || o.application_status === "interested")
    );
  }, []);

  const refreshJobs = useCallback(
    async (opts: { silent?: boolean } = {}) => {
      if (!opts.silent) setRefreshing(true);
      try {
        await api.runDiscovery();
        const status = await api.getGmailStatus();
        setGmailStatus(status);
        await loadFeed();
      } catch (e) {
        if (!opts.silent) {
          setError(e instanceof ApiError ? e.detail : e instanceof Error ? e.message : "Failed");
        }
      } finally {
        if (!opts.silent) setRefreshing(false);
      }
    },
    [loadFeed]
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const status = await api.getGmailStatus();
      setGmailStatus(status);
      await loadFeed();

      if (status.connected) {
        const staleMs = STALE_SYNC_MINUTES * 60 * 1000;
        const lastSync = status.last_sync_at ? new Date(status.last_sync_at).getTime() : 0;
        if (Date.now() - lastSync > staleMs) {
          void refreshJobs({ silent: true });
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load your recommended jobs");
    } finally {
      setLoading(false);
    }
  }, [loadFeed, refreshJobs]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional: initial data load on mount
    void load();
  }, [load]);

  useEffect(() => {
    if (!preparingJobId) return;
    const interval = setInterval(() => {
      setPreparingMessageIndex((i) => (i + 1) % PREPARING_MESSAGES.length);
    }, 1800);
    return () => clearInterval(interval);
  }, [preparingJobId]);

  async function handlePrepare(item: OpportunityItem) {
    if (!item.job_id) return;
    setPreparingJobId(item.discovered_job_id);
    setPreparingMessageIndex(0);
    setError(null);
    try {
      await Promise.all([
        api.prepareApplication(item.job_id),
        api.setApplicationStatus(item.job_id, "applying"),
      ]);
      router.push(`/jobs/${item.job_id}/apply`);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : e instanceof Error ? e.message : "Failed");
      setPreparingJobId(null);
    }
  }

  async function handleNotInterested(item: OpportunityItem) {
    try {
      await api.ignoreOpportunity(item.discovered_job_id);
      setOpportunities((prev) => prev.filter((o) => o.discovered_job_id !== item.discovered_job_id));
    } catch {
      // non-critical - leave the card visible if this fails
    }
  }

  const strongMatchCount = opportunities.filter(
    (o) => o.priority && DEFAULT_VISIBLE_PRIORITIES.includes(o.priority)
  ).length;
  const lowPriorityCount = opportunities.length - strongMatchCount;

  if (loading) return <Spinner />;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">Jobs for you</h1>
          <p className="mt-1 text-sm text-zinc-400">
            {opportunities.length} new job{opportunities.length === 1 ? "" : "s"} found ·{" "}
            {strongMatchCount} strong match{strongMatchCount === 1 ? "" : "es"}
          </p>
        </div>
        {gmailStatus?.connected && (
          <div className="flex items-center gap-3 text-sm text-zinc-500">
            <span>Last checked: {formatRelativeTime(gmailStatus.last_sync_at)}</span>
            <SecondaryButton onClick={() => refreshJobs()} disabled={refreshing}>
              {refreshing ? "Refreshing..." : "Refresh jobs"}
            </SecondaryButton>
          </div>
        )}
      </div>

      {error && <ErrorBanner message={error} />}

      {preparingJobId && (
        <div className="rounded-lg border border-indigo-800/50 bg-indigo-950/30 px-4 py-3 text-sm text-indigo-300">
          Preparing application... {PREPARING_MESSAGES[preparingMessageIndex]}
        </div>
      )}

      {gmailStatus && !gmailStatus.connected && (
        <EmptyState
          title="Connect Gmail to import your SEEK and LinkedIn job alerts."
          subtitle={
            <>
              Once connected, new alerts are picked up automatically - no need to run anything
              yourself.{" "}
              <Link href="/settings" className="text-indigo-400 hover:underline">
                Go to Settings →
              </Link>
            </>
          }
        />
      )}

      {gmailStatus?.connected &&
        opportunities.length === 0 &&
        (
          <EmptyState
            title="No strong new matches today."
            subtitle="Checking your SEEK and LinkedIn alerts automatically - check back soon, or use Refresh jobs above."
          />
        )}

      {gmailStatus?.connected &&
        GROUPS.map((group) => {
          const items = opportunities.filter(
            (o) => o.priority && group.priorities.includes(o.priority)
          );
          if (items.length === 0) return null;
          return (
            <div key={group.key} className="space-y-3">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
                {group.title}
              </h2>
              {items.map((item) => (
                <SimpleJobCard
                  key={item.discovered_job_id}
                  item={item}
                  preparing={preparingJobId === item.discovered_job_id}
                  onPrepare={() => handlePrepare(item)}
                  onNotInterested={() => handleNotInterested(item)}
                />
              ))}
            </div>
          );
        })}

      {gmailStatus?.connected && showAll && lowPriorityCount > 0 && (
        <div className="space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Low priority
          </h2>
          {opportunities
            .filter((o) => o.priority === "low_priority")
            .map((item) => (
              <SimpleJobCard
                key={item.discovered_job_id}
                item={item}
                preparing={preparingJobId === item.discovered_job_id}
                onPrepare={() => handlePrepare(item)}
                onNotInterested={() => handleNotInterested(item)}
              />
            ))}
        </div>
      )}

      {gmailStatus?.connected && !showAll && lowPriorityCount > 0 && (
        <Card className="flex items-center justify-between">
          <p className="text-sm text-zinc-400">
            {lowPriorityCount} more lower-priority match{lowPriorityCount === 1 ? "" : "es"} hidden.
          </p>
          <SecondaryButton onClick={() => setShowAll(true)}>Show more</SecondaryButton>
        </Card>
      )}
    </div>
  );
}
