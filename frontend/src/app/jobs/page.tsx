"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  Card,
  EmptyState,
  ErrorBanner,
  PrimaryButton,
  SecondaryButton,
  SectionHeading,
  Spinner,
} from "@/components/ui";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { Job } from "@/lib/types";

function AddJobForm({ onCreated }: { onCreated: (job: Job) => void }) {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    title: "",
    company: "",
    location: "",
    source_url: "",
    raw_description: "",
  });

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const job = await api.createJob({
        title: form.title,
        company: form.company,
        location: form.location || null,
        source_url: form.source_url || null,
        raw_description: form.raw_description,
      });
      onCreated(job);
      setForm({ title: "", company: "", location: "", source_url: "", raw_description: "" });
      setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create job");
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) {
    return <PrimaryButton onClick={() => setOpen(true)}>+ Add job</PrimaryButton>;
  }

  return (
    <Card className="w-full max-w-2xl">
      <SectionHeading title="Paste a job description" />
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-zinc-400">Title *</label>
            <input
              required
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none"
              placeholder="Backend Engineer"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-zinc-400">Company *</label>
            <input
              required
              value={form.company}
              onChange={(e) => setForm({ ...form, company: e.target.value })}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none"
              placeholder="Acme Corp"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-zinc-400">Location</label>
            <input
              value={form.location}
              onChange={(e) => setForm({ ...form, location: e.target.value })}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none"
              placeholder="Melbourne, VIC"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-zinc-400">Source URL</label>
            <input
              value={form.source_url}
              onChange={(e) => setForm({ ...form, source_url: e.target.value })}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none"
              placeholder="https://..."
            />
          </div>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-zinc-400">
            Job description *
          </label>
          <textarea
            required
            rows={8}
            value={form.raw_description}
            onChange={(e) => setForm({ ...form, raw_description: e.target.value })}
            className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none"
            placeholder="Paste the full job description here..."
          />
        </div>
        {error && <ErrorBanner message={error} />}
        <div className="flex gap-3">
          <PrimaryButton type="submit" disabled={submitting}>
            {submitting ? "Saving..." : "Save job"}
          </PrimaryButton>
          <SecondaryButton onClick={() => setOpen(false)} disabled={submitting}>
            Cancel
          </SecondaryButton>
        </div>
      </form>
    </Card>
  );
}

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listJobs()
      .then(setJobs)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">Jobs</h1>
          <p className="mt-1 text-sm text-zinc-400">Paste in a job description to get started.</p>
        </div>
      </div>

      <AddJobForm onCreated={(job) => setJobs([job, ...jobs])} />

      {loading && <Spinner />}
      {error && <ErrorBanner message={error} />}

      {!loading && !error && (
        <Card>
          <SectionHeading title={`${jobs.length} job${jobs.length === 1 ? "" : "s"}`} />
          {jobs.length === 0 ? (
            <EmptyState
              title="No jobs yet"
              subtitle="Use 'Add job' above to paste your first job description."
            />
          ) : (
            <div className="divide-y divide-zinc-800">
              {jobs.map((job) => (
                <Link
                  key={job.id}
                  href={`/jobs/${job.id}`}
                  className="flex items-center justify-between gap-4 py-3 transition hover:bg-zinc-800/40"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-zinc-200">{job.title}</p>
                    <p className="truncate text-xs text-zinc-500">
                      {job.company}
                      {job.location ? ` · ${job.location}` : ""}
                    </p>
                  </div>
                  <span className="shrink-0 text-xs text-zinc-500">
                    {formatDate(job.created_at)}
                  </span>
                </Link>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
