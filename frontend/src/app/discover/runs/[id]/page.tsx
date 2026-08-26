"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Card, ErrorBanner, SectionHeading, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { DISCOVERED_STATUS_LABEL, formatDateTime } from "@/lib/format";
import type { DiscoveredJob, DiscoveryRun } from "@/lib/types";

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div>
      <p className="text-xs text-zinc-500">{label}</p>
      <p className="text-lg font-semibold text-zinc-100">{value}</p>
    </div>
  );
}

function durationLabel(run: DiscoveryRun): string {
  if (!run.started_at || !run.finished_at) return "-";
  const ms = new Date(run.finished_at).getTime() - new Date(run.started_at).getTime();
  if (Number.isNaN(ms) || ms < 0) return "-";
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

function JobRow({ job }: { job: DiscoveredJob }) {
  return (
    <tr className="border-b border-zinc-800/60 last:border-0">
      <td className="py-2 pr-4">
        <p className="text-sm font-medium text-zinc-200">{job.title}</p>
        <p className="text-xs text-zinc-500">
          {job.company}
          {job.location ? ` · ${job.location}` : ""}
        </p>
      </td>
      <td className="py-2 pr-4 text-xs text-zinc-400">{job.source}</td>
      <td className="py-2 pr-4 text-xs text-zinc-400">{DISCOVERED_STATUS_LABEL[job.status]}</td>
      <td className="py-2 pr-4 text-xs text-zinc-400">
        {job.analysis_priority != null ? job.analysis_priority.toFixed(0) : "-"}
      </td>
      <td className="py-2 pr-4 text-xs text-zinc-500">{job.prefilter_reason ?? "-"}</td>
      <td className="py-2 text-xs text-zinc-500">
        {job.job_id ? (
          <Link href={`/jobs/${job.job_id}`} className="text-indigo-400 hover:underline">
            View job ↗
          </Link>
        ) : (
          "-"
        )}
      </td>
    </tr>
  );
}

export default function DiscoveryRunDetailPage() {
  const params = useParams<{ id: string }>();
  const runId = params?.id;
  const [run, setRun] = useState<DiscoveryRun | null>(null);
  const [jobs, setJobs] = useState<DiscoveredJob[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional: reload run detail when the route param changes
    setLoading(true);
    Promise.all([api.getDiscoveryRun(runId), api.getDiscoveryRunJobs(runId)])
      .then(([r, j]) => {
        setRun(r);
        setJobs(j);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [runId]);

  if (loading) return <Spinner />;
  if (error) return <ErrorBanner message={error} />;
  if (!run) return null;

  const statuses = Array.from(new Set(jobs.map((j) => j.status)));
  const filteredJobs = statusFilter === "all" ? jobs : jobs.filter((j) => j.status === statusFilter);

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Link href="/discover" className="text-xs text-indigo-400 hover:underline">
            ← Back to Discover
          </Link>
          <h1 className="mt-2 text-2xl font-semibold text-zinc-100">
            Discovery run · {formatDateTime(run.started_at)}
          </h1>
          <p className="mt-1 text-sm text-zinc-400">
            Triggered {run.triggered_by === "scheduled" ? "automatically (scheduled)" : "manually"}{" "}
            · Sources: {run.sources_used.join(", ") || "none"} · Duration: {durationLabel(run)}
          </p>
        </div>
        <span
          className={`rounded-full px-3 py-1 text-xs font-medium ${
            run.status === "failed"
              ? "bg-rose-500/15 text-rose-400"
              : run.status === "running"
                ? "bg-amber-500/15 text-amber-400"
                : "bg-emerald-500/15 text-emerald-400"
          }`}
        >
          {run.status}
        </span>
      </div>

      {run.error_message && <ErrorBanner message={run.error_message} />}

      <Card>
        <SectionHeading title="Counts" />
        <div className="grid grid-cols-3 gap-4 text-sm sm:grid-cols-6">
          <Stat label="Retrieved" value={run.counts.retrieved} />
          <Stat label="New" value={run.counts.new} />
          <Stat label="Duplicates" value={run.counts.duplicates} />
          <Stat label="Filtered out" value={run.counts.prefilter_rejected} />
          <Stat label="Eligible" value={run.counts.eligible} />
          <Stat label="Analysed" value={run.counts.analysed} />
          <Stat label="Deferred" value={run.counts.deferred} />
          <Stat label="Failed" value={run.counts.failed} />
          <Stat label="Strong Apply+" value={run.counts.strong_apply_or_better} />
          <Stat label="AI calls" value={run.counts.ai_calls} />
          <Stat label="Input tokens" value={run.counts.ai_input_tokens} />
          <Stat label="Output tokens" value={run.counts.ai_output_tokens} />
          <Stat label="Estimated cost" value={`$${run.estimated_cost_usd.toFixed(4)}`} />
        </div>
      </Card>

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <SectionHeading title="Jobs seen in this run" />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="mb-5 rounded-lg border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-xs text-zinc-200 focus:border-indigo-500 focus:outline-none"
          >
            <option value="all">All statuses ({jobs.length})</option>
            {statuses.map((s) => (
              <option key={s} value={s}>
                {DISCOVERED_STATUS_LABEL[s]} ({jobs.filter((j) => j.status === s).length})
              </option>
            ))}
          </select>
        </div>
        {filteredJobs.length === 0 ? (
          <p className="py-6 text-center text-sm text-zinc-500">No jobs match this filter.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-zinc-800 text-xs text-zinc-500">
                  <th className="pb-2 pr-4 font-medium">Job</th>
                  <th className="pb-2 pr-4 font-medium">Source</th>
                  <th className="pb-2 pr-4 font-medium">Status</th>
                  <th className="pb-2 pr-4 font-medium">Priority</th>
                  <th className="pb-2 pr-4 font-medium">Reason</th>
                  <th className="pb-2 font-medium"></th>
                </tr>
              </thead>
              <tbody>
                {filteredJobs.map((job) => (
                  <JobRow key={job.id} job={job} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
