"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { RecommendationBadge } from "@/components/RecommendationBadge";
import { Card, EmptyState, ErrorBanner, SectionHeading, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDate, scoreColorClass } from "@/lib/format";
import type { ApplicationStatus, JobListItem, Recommendation } from "@/lib/types";

const SECTIONS: { statuses: ApplicationStatus[]; title: string }[] = [
  { statuses: ["interested"], title: "Ready to Apply" },
  { statuses: ["applying"], title: "Preparing" },
  { statuses: ["applied"], title: "Applied" },
  { statuses: ["interview"], title: "Interview" },
  { statuses: ["offer"], title: "Offer" },
  { statuses: ["rejected", "withdrawn"], title: "Closed" },
];

function ApplicationRow({ item }: { item: JobListItem }) {
  return (
    <Link
      href={`/jobs/${item.id}/apply`}
      className="flex items-center justify-between gap-4 rounded-lg px-3 py-2.5 transition hover:bg-zinc-800/60"
    >
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-zinc-200">{item.title}</p>
        <p className="truncate text-xs text-zinc-500">
          {item.company}
          {item.location ? ` · ${item.location}` : ""} · {formatDate(item.created_at)}
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

export default function ApplicationsPage() {
  const [jobs, setJobs] = useState<JobListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getPrioritizedJobs()
      .then((all) => setJobs(all.filter((j) => j.application_status && j.application_status !== "ignored")))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spinner />;
  if (error) return <ErrorBanner message={error} />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100">Applications</h1>
        <p className="mt-1 text-sm text-zinc-400">Your personal job-application tracker.</p>
      </div>

      {jobs.length === 0 ? (
        <EmptyState
          title="No applications in progress yet"
          subtitle="Prepare an application from your recommended jobs to see it tracked here."
        />
      ) : (
        SECTIONS.map((section) => {
          const items = jobs.filter((j) => section.statuses.includes(j.application_status!));
          if (items.length === 0) return null;
          return (
            <Card key={section.title}>
              <SectionHeading title={`${section.title} (${items.length})`} />
              <div className="space-y-1">
                {items.map((item) => (
                  <ApplicationRow key={item.id} item={item} />
                ))}
              </div>
            </Card>
          );
        })
      )}
    </div>
  );
}
