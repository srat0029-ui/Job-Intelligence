"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { SimpleJobCard } from "@/components/SimpleJobCard";
import { Card, EmptyState, ErrorBanner, SecondaryButton, Spinner } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import type { JobPriority, OpportunityItem } from "@/lib/types";

// Hide stretch/low-priority roles from the default view - Part 7/21 of the
// simplification brief: quality over quantity, no manual filtering needed
// for the everyday case. "Show more" reveals everything analysed.
const DEFAULT_VISIBLE_PRIORITIES: JobPriority[] = ["apply_asap", "strong_apply", "apply"];

const PREPARING_MESSAGES = [
  "Analysing fit...",
  "Researching the company...",
  "Tailoring your application...",
];

export default function HomePage() {
  const router = useRouter();
  const [opportunities, setOpportunities] = useState<OpportunityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [preparingJobId, setPreparingJobId] = useState<string | null>(null);
  const [preparingMessageIndex, setPreparingMessageIndex] = useState(0);

  async function load() {
    setLoading(true);
    setError(null);
    try {
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
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load your recommended jobs");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional: initial data load on mount
    void load();
  }, []);

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

  const strongMatches = opportunities.filter(
    (o) => o.priority && DEFAULT_VISIBLE_PRIORITIES.includes(o.priority)
  );
  const visible = showAll ? opportunities : strongMatches;

  if (loading) return <Spinner />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100">My Recommended Jobs</h1>
        <p className="mt-1 text-sm text-zinc-400">
          Australian roles ranked for you - best first.
        </p>
      </div>

      {error && <ErrorBanner message={error} />}

      {preparingJobId && (
        <div className="rounded-lg border border-indigo-800/50 bg-indigo-950/30 px-4 py-3 text-sm text-indigo-300">
          Preparing application... {PREPARING_MESSAGES[preparingMessageIndex]}
        </div>
      )}

      {visible.length === 0 && (
        <EmptyState
          title={
            opportunities.length === 0
              ? "No strong new matches today."
              : "No strong new matches today."
          }
          subtitle={
            opportunities.length === 0
              ? "Run discovery from the Discover page (under Advanced) to look for new roles."
              : "Showing recent opportunities below instead."
          }
        />
      )}

      {visible.length === 0 && opportunities.length > 0 && (
        <div className="space-y-3">
          {opportunities.slice(0, 5).map((item) => (
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

      {visible.length > 0 && (
        <div className="space-y-3">
          {visible.map((item) => (
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

      {!showAll && opportunities.length > strongMatches.length && (
        <Card className="flex items-center justify-between">
          <p className="text-sm text-zinc-400">
            {opportunities.length - strongMatches.length} more lower-priority match(es) hidden.
          </p>
          <SecondaryButton onClick={() => setShowAll(true)}>Show more</SecondaryButton>
        </Card>
      )}
    </div>
  );
}
