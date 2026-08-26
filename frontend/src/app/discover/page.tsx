"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApplicationStatusSelector } from "@/components/ApplicationStatusSelector";
import { PriorityBadge } from "@/components/RecommendationBadge";
import { AddButton, Field, RemoveButton, TagListInput, TextInput } from "@/components/form";
import {
  Card,
  EmptyState,
  ErrorBanner,
  PrimaryButton,
  SecondaryButton,
  SectionHeading,
  Spinner,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { DISCOVERED_STATUS_LABEL, formatDate, formatDateTime, scoreColorClass } from "@/lib/format";
import type { DiscoveryRun, JobPriority, OpportunityItem, SearchProfile } from "@/lib/types";

const EMPTY_PROFILE: SearchProfile = {
  name: "",
  keywords: [],
  keyword_groups: [],
  locations: [],
  location_priority: {},
  include_remote: true,
  max_experience_level: null,
  excluded_keywords: [],
  enabled: true,
  source_config: {},
};

const EXPERIENCE_LEVELS = ["intern", "graduate", "junior", "mid", "senior", "lead", "staff_plus"];

const PRIORITY_SECTION_ORDER: JobPriority[] = [
  "apply_asap",
  "strong_apply",
  "apply",
  "stretch",
  "low_priority",
];

const PRIORITY_SECTION_LABEL: Record<JobPriority, string> = {
  apply_asap: "Apply ASAP",
  strong_apply: "Strong matches",
  apply: "Worth applying",
  stretch: "Stretch opportunities",
  low_priority: "Low priority",
};

function SearchProfileForm({
  initial,
  onSave,
  onCancel,
}: {
  initial: SearchProfile;
  onSave: (p: SearchProfile) => void;
  onCancel: () => void;
}) {
  const [profile, setProfile] = useState(initial);
  return (
    <div className="space-y-3 rounded-lg border border-zinc-800 p-4">
      <div className="grid grid-cols-2 gap-3">
        <Field label="Profile name">
          <TextInput value={profile.name} onChange={(v) => setProfile({ ...profile, name: v })} />
        </Field>
        <Field label="Max experience level">
          <select
            value={profile.max_experience_level ?? ""}
            onChange={(e) =>
              setProfile({
                ...profile,
                max_experience_level: (e.target.value || null) as SearchProfile["max_experience_level"],
              })
            }
            className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none"
          >
            <option value="">No ceiling</option>
            {EXPERIENCE_LEVELS.map((lvl) => (
              <option key={lvl} value={lvl}>
                {lvl}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <Field label="Keywords (comma separated - alternate titles welcome)">
        <TagListInput
          values={profile.keywords}
          onChange={(v) => setProfile({ ...profile, keywords: v })}
          placeholder="graduate data scientist, junior ai engineer"
        />
      </Field>
      <Field label="Locations (comma separated)">
        <TagListInput
          values={profile.locations}
          onChange={(v) => setProfile({ ...profile, locations: v })}
          placeholder="Melbourne, Hobart, Sydney"
        />
      </Field>
      <Field label="Excluded keywords (comma separated)">
        <TagListInput
          values={profile.excluded_keywords}
          onChange={(v) => setProfile({ ...profile, excluded_keywords: v })}
        />
      </Field>
      <label className="flex items-center gap-2 text-sm text-zinc-300">
        <input
          type="checkbox"
          checked={profile.include_remote}
          onChange={(e) => setProfile({ ...profile, include_remote: e.target.checked })}
        />
        Include remote roles
      </label>
      <div className="flex gap-3">
        <PrimaryButton onClick={() => onSave(profile)}>Save</PrimaryButton>
        <SecondaryButton onClick={onCancel}>Cancel</SecondaryButton>
      </div>
    </div>
  );
}

function SearchProfilesPanel({
  profiles,
  onChanged,
}: {
  profiles: SearchProfile[];
  onChanged: () => void;
}) {
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  async function handleCreate(p: SearchProfile) {
    await api.createSearchProfile(p);
    setAdding(false);
    onChanged();
  }

  async function handleUpdate(id: string, p: SearchProfile) {
    await api.updateSearchProfile(id, p);
    setEditingId(null);
    onChanged();
  }

  async function handleToggle(p: SearchProfile) {
    if (!p.id) return;
    await api.updateSearchProfile(p.id, { ...p, enabled: !p.enabled });
    onChanged();
  }

  async function handleDelete(id: string) {
    await api.deleteSearchProfile(id);
    onChanged();
  }

  return (
    <Card>
      <SectionHeading
        title="Search profiles"
        subtitle="Saved keyword/location searches that discovery runs against"
        action={!adding && <AddButton label="+ New search profile" onClick={() => setAdding(true)} />}
      />
      {adding && (
        <div className="mb-4">
          <SearchProfileForm
            initial={EMPTY_PROFILE}
            onSave={handleCreate}
            onCancel={() => setAdding(false)}
          />
        </div>
      )}
      {profiles.length === 0 && !adding ? (
        <EmptyState
          title="No search profiles yet"
          subtitle="Add one to tell discovery what jobs to look for."
        />
      ) : (
        <div className="space-y-3">
          {profiles.map((p) =>
            editingId === p.id ? (
              <SearchProfileForm
                key={p.id}
                initial={p}
                onSave={(updated) => p.id && handleUpdate(p.id, updated)}
                onCancel={() => setEditingId(null)}
              />
            ) : (
              <div
                key={p.id}
                className="flex items-center justify-between gap-4 rounded-lg border border-zinc-800 px-4 py-3"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-zinc-200">
                    {p.name}{" "}
                    {!p.enabled && <span className="text-xs text-zinc-500">(disabled)</span>}
                  </p>
                  <p className="truncate text-xs text-zinc-500">
                    {p.keywords.join(", ") || "no keywords"} ·{" "}
                    {p.locations.join(", ") || "any location"}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <SecondaryButton onClick={() => handleToggle(p)}>
                    {p.enabled ? "Disable" : "Enable"}
                  </SecondaryButton>
                  <SecondaryButton onClick={() => setEditingId(p.id ?? null)}>Edit</SecondaryButton>
                  <RemoveButton onClick={() => p.id && handleDelete(p.id)} />
                </div>
              </div>
            )
          )}
        </div>
      )}
    </Card>
  );
}

function RecentRunsPanel({ runs }: { runs: DiscoveryRun[] }) {
  if (runs.length === 0) return null;
  return (
    <Card>
      <SectionHeading title="Recent discovery runs" />
      <div className="space-y-1">
        {runs.slice(0, 8).map((run) => (
          <Link
            key={run.id}
            href={`/discover/runs/${run.id}`}
            className="flex items-center justify-between gap-4 rounded-lg px-3 py-2.5 text-sm transition hover:bg-zinc-800/60"
          >
            <div className="min-w-0">
              <span className="text-zinc-200">{formatDateTime(run.started_at)}</span>
              <span className="ml-2 text-xs text-zinc-500">
                {run.triggered_by === "scheduled" ? "scheduled" : "manual"}
              </span>
            </div>
            <div className="flex shrink-0 items-center gap-4 text-xs text-zinc-500">
              <span>{run.counts.new} new</span>
              <span>{run.counts.analysed} analysed</span>
              <span
                className={
                  run.status === "failed"
                    ? "text-rose-400"
                    : run.status === "running"
                      ? "text-amber-400"
                      : "text-emerald-400"
                }
              >
                {run.status}
              </span>
            </div>
          </Link>
        ))}
      </div>
    </Card>
  );
}

function OpportunityCard({
  item,
  onMarkReviewed,
  onIgnore,
}: {
  item: OpportunityItem;
  onMarkReviewed: (id: string) => void;
  onIgnore: (id: string) => void;
}) {
  const analysed = item.status === "analysed";
  const content = (
    <Card className="transition hover:border-zinc-700">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-4">
          {item.overall_score != null && (
            <div className={`text-3xl font-bold ${scoreColorClass(item.overall_score)}`}>
              {item.overall_score.toFixed(0)}
            </div>
          )}
          <div>
            <p className="text-sm font-semibold text-zinc-100">
              {item.title}
              {!item.reviewed_at && (
                <span className="ml-2 rounded-full bg-indigo-500/15 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-indigo-300 ring-1 ring-indigo-500/30">
                  New
                </span>
              )}
            </p>
            <p className="text-xs text-zinc-500">
              {item.company}
              {item.location ? ` · ${item.location}` : ""}
            </p>
            <p className="mt-1 text-xs text-zinc-600">
              Posted {formatDate(item.published_at)} · Discovered {formatDate(item.discovered_at)}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          {item.priority && <PriorityBadge priority={item.priority} />}
          {!analysed && (
            <span className="text-xs text-zinc-500">{DISCOVERED_STATUS_LABEL[item.status]}</span>
          )}
        </div>
      </div>

      {analysed && (
        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          {item.strong_matches.length > 0 && (
            <div>
              <p className="text-xs font-medium text-zinc-500">Strong matches</p>
              <p className="text-sm text-zinc-300">{item.strong_matches.join(", ")}</p>
            </div>
          )}
          {item.main_gap && (
            <div>
              <p className="text-xs font-medium text-zinc-500">Main gap</p>
              <p className="text-sm text-rose-400">{item.main_gap}</p>
            </div>
          )}
        </div>
      )}

      {item.why_summary.length > 0 && (
        <ul className="mt-3 list-inside list-disc space-y-0.5 text-xs text-zinc-400">
          {item.why_summary.map((line, i) => (
            <li key={i}>{line}</li>
          ))}
        </ul>
      )}

      {item.prefilter_reason && (
        <p className="mt-3 rounded-lg bg-zinc-800/50 px-3 py-2 text-xs text-zinc-500">
          Filtered out: {item.prefilter_reason}
        </p>
      )}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        {/* stopPropagation on the wrapper, not the buttons themselves, since
            SecondaryButton's onClick prop takes no event arg (it's a plain
            () => void) - the card as a whole may be wrapped in a Link. */}
        <div
          className="flex items-center gap-2"
          onClick={(e) => e.stopPropagation()}
          onKeyDown={(e) => e.stopPropagation()}
        >
          {item.job_id ? (
            <ApplicationStatusSelector jobId={item.job_id} status={item.application_status} />
          ) : (
            <span />
          )}
          {!item.reviewed_at && (
            <SecondaryButton onClick={() => onMarkReviewed(item.discovered_job_id)}>
              Mark reviewed
            </SecondaryButton>
          )}
          <SecondaryButton onClick={() => onIgnore(item.discovered_job_id)}>Ignore</SecondaryButton>
        </div>
        {item.source_url && (
          <a
            href={item.source_url}
            target="_blank"
            rel="noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="text-xs text-indigo-400 hover:underline"
          >
            View posting ↗
          </a>
        )}
      </div>
    </Card>
  );

  return item.job_id ? (
    <Link href={`/jobs/${item.job_id}`} className="block">
      {content}
    </Link>
  ) : (
    content
  );
}

function groupByPriority(items: OpportunityItem[]): { label: string; items: OpportunityItem[] }[] {
  const groups: { label: string; items: OpportunityItem[] }[] = [];
  for (const priority of PRIORITY_SECTION_ORDER) {
    const matching = items.filter((i) => i.priority === priority);
    if (matching.length > 0) {
      groups.push({ label: PRIORITY_SECTION_LABEL[priority], items: matching });
    }
  }
  const unscored = items.filter((i) => !i.priority);
  if (unscored.length > 0) {
    groups.push({ label: "Awaiting analysis / not scored", items: unscored });
  }
  return groups;
}

export default function DiscoverPage() {
  const [opportunities, setOpportunities] = useState<OpportunityItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [profiles, setProfiles] = useState<SearchProfile[]>([]);
  const [runs, setRuns] = useState<DiscoveryRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [lastRun, setLastRun] = useState<DiscoveryRun | null>(null);
  const [showRejected, setShowRejected] = useState(false);
  const [reviewedFilter, setReviewedFilter] = useState<"unreviewed" | "reviewed" | "all">(
    "unreviewed"
  );
  const [sortBy, setSortBy] = useState("score");
  const [groupByPriorityEnabled, setGroupByPriorityEnabled] = useState(true);

  async function loadAll() {
    setLoading(true);
    setError(null);
    try {
      const [opp, profs, recentRuns] = await Promise.all([
        api.listOpportunities({
          sortBy,
          includeRejected: showRejected,
          reviewed: reviewedFilter === "all" ? undefined : reviewedFilter === "reviewed",
          page,
          pageSize,
        }),
        api.listSearchProfiles(),
        api.listDiscoveryRuns(),
      ]);
      setOpportunities(opp.items);
      setTotal(opp.total);
      setProfiles(profs);
      setRuns(recentRuns);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional: reload feed whenever sort/filter/page changes
    void loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sortBy, showRejected, reviewedFilter, page]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional: reset to page 1 when filters change
    setPage(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sortBy, showRejected, reviewedFilter]);

  async function handleRunDiscovery() {
    setRunning(true);
    setError(null);
    try {
      const run = await api.runDiscovery();
      setLastRun(run);
      await loadAll();
    } catch (e) {
      if (e instanceof ApiError) {
        setError(e.detail);
      } else {
        setError(e instanceof Error ? e.message : "Discovery run failed");
      }
    } finally {
      setRunning(false);
    }
  }

  async function handleMarkReviewed(id: string) {
    await api.markOpportunityReviewed(id);
    await loadAll();
  }

  async function handleIgnore(id: string) {
    await api.ignoreOpportunity(id);
    await loadAll();
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const sections = groupByPriorityEnabled ? groupByPriority(opportunities) : null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">Discover</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Automatically found opportunities, ranked by fit.
          </p>
        </div>
        <PrimaryButton onClick={handleRunDiscovery} disabled={running}>
          {running ? "Running discovery..." : "Run discovery"}
        </PrimaryButton>
      </div>

      {error && <ErrorBanner message={error} />}

      {lastRun && (
        <Card>
          <SectionHeading
            title="Last run summary"
            action={
              lastRun.id && (
                <Link
                  href={`/discover/runs/${lastRun.id}`}
                  className="text-xs text-indigo-400 hover:underline"
                >
                  View details ↗
                </Link>
              )
            }
          />
          <div className="grid grid-cols-3 gap-4 text-sm sm:grid-cols-6">
            <Stat label="Retrieved" value={lastRun.counts.retrieved} />
            <Stat label="New" value={lastRun.counts.new} />
            <Stat label="Duplicates" value={lastRun.counts.duplicates} />
            <Stat label="Filtered out" value={lastRun.counts.prefilter_rejected} />
            <Stat label="Eligible" value={lastRun.counts.eligible} />
            <Stat label="Analysed" value={lastRun.counts.analysed} />
            <Stat label="Deferred" value={lastRun.counts.deferred} />
            <Stat label="Failed" value={lastRun.counts.failed} />
            <Stat label="Strong Apply+" value={lastRun.counts.strong_apply_or_better} />
            <Stat label="Cost" value={`$${lastRun.estimated_cost_usd.toFixed(4)}`} />
          </div>
        </Card>
      )}

      <SearchProfilesPanel profiles={profiles} onChanged={loadAll} />

      <RecentRunsPanel runs={runs} />

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <SectionHeading
            title={reviewedFilter === "unreviewed" ? "Today's Opportunities" : "Opportunities"}
          />
          <div className="mb-5 flex flex-wrap items-center gap-3">
            <select
              value={reviewedFilter}
              onChange={(e) => setReviewedFilter(e.target.value as typeof reviewedFilter)}
              className="rounded-lg border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-xs text-zinc-200 focus:border-indigo-500 focus:outline-none"
            >
              <option value="unreviewed">Unreviewed only</option>
              <option value="reviewed">Reviewed only</option>
              <option value="all">All</option>
            </select>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="rounded-lg border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-xs text-zinc-200 focus:border-indigo-500 focus:outline-none"
            >
              <option value="score">Sort: Fit score</option>
              <option value="posted_date">Sort: Date posted</option>
              <option value="discovered_date">Sort: Discovery date</option>
              <option value="company">Sort: Company</option>
              <option value="title">Sort: Title</option>
              <option value="location">Sort: Location</option>
            </select>
            <label className="flex items-center gap-1.5 text-xs text-zinc-400">
              <input
                type="checkbox"
                checked={showRejected}
                onChange={(e) => setShowRejected(e.target.checked)}
              />
              Show filtered-out jobs
            </label>
            <label className="flex items-center gap-1.5 text-xs text-zinc-400">
              <input
                type="checkbox"
                checked={groupByPriorityEnabled}
                onChange={(e) => setGroupByPriorityEnabled(e.target.checked)}
              />
              Group by priority
            </label>
          </div>
        </div>

        {loading && <Spinner />}
        {!loading && opportunities.length === 0 && (
          <EmptyState
            title="No opportunities yet"
            subtitle={
              profiles.length === 0
                ? "Add a search profile above, then run discovery."
                : "Run discovery to fetch and analyse jobs for your search profiles."
            }
          />
        )}
        {!loading && opportunities.length > 0 && sections && (
          <div className="space-y-6">
            {sections.map((section) => (
              <div key={section.label}>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                  {section.label} ({section.items.length})
                </p>
                <div className="space-y-3">
                  {section.items.map((item) => (
                    <OpportunityCard
                      key={item.discovered_job_id}
                      item={item}
                      onMarkReviewed={handleMarkReviewed}
                      onIgnore={handleIgnore}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
        {!loading && opportunities.length > 0 && !sections && (
          <div className="space-y-3">
            {opportunities.map((item) => (
              <OpportunityCard
                key={item.discovered_job_id}
                item={item}
                onMarkReviewed={handleMarkReviewed}
                onIgnore={handleIgnore}
              />
            ))}
          </div>
        )}

        {!loading && total > 0 && (
          <div className="mt-5 flex items-center justify-between border-t border-zinc-800 pt-4 text-xs text-zinc-400">
            <span>
              Page {page} of {totalPages} · {total} total
            </span>
            <div className="flex gap-2">
              <SecondaryButton onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1}>
                Previous
              </SecondaryButton>
              <SecondaryButton
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
              >
                Next
              </SecondaryButton>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div>
      <p className="text-xs text-zinc-500">{label}</p>
      <p className="text-lg font-semibold text-zinc-100">{value}</p>
    </div>
  );
}
