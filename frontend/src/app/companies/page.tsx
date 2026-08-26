"use client";

import { useEffect, useState } from "react";
import { CompanyPriorityBadge, SourceHealthBadge } from "@/components/RecommendationBadge";
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
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { ATSType, CompanyPriority, CompanyWatchlistEntry, SourceHealth } from "@/lib/types";

const EMPTY_ENTRY: CompanyWatchlistEntry = {
  company_name: "",
  enabled: true,
  priority: "normal",
  careers_url: null,
  ats_type: "lever",
  ats_identifier: "",
  preferred_locations: [],
  notes: null,
};

const ATS_TYPES: ATSType[] = ["lever", "greenhouse"];
const PRIORITIES: CompanyPriority[] = ["high", "normal", "low"];

function WatchlistEntryForm({
  initial,
  onSave,
  onCancel,
}: {
  initial: CompanyWatchlistEntry;
  onSave: (e: CompanyWatchlistEntry) => void;
  onCancel: () => void;
}) {
  const [entry, setEntry] = useState(initial);
  return (
    <div className="space-y-3 rounded-lg border border-zinc-800 p-4">
      <div className="grid grid-cols-2 gap-3">
        <Field label="Company name">
          <TextInput
            value={entry.company_name}
            onChange={(v) => setEntry({ ...entry, company_name: v })}
          />
        </Field>
        <Field label="Priority">
          <select
            value={entry.priority}
            onChange={(e) => setEntry({ ...entry, priority: e.target.value as CompanyPriority })}
            className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none"
          >
            {PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="ATS type">
          <select
            value={entry.ats_type}
            onChange={(e) => setEntry({ ...entry, ats_type: e.target.value as ATSType })}
            className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none"
          >
            {ATS_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </Field>
        <Field label="ATS identifier (Lever site / Greenhouse board token)">
          <TextInput
            value={entry.ats_identifier}
            onChange={(v) => setEntry({ ...entry, ats_identifier: v })}
            placeholder="e.g. acme"
          />
        </Field>
      </div>
      <Field label="Careers page URL (optional)">
        <TextInput
          value={entry.careers_url ?? ""}
          onChange={(v) => setEntry({ ...entry, careers_url: v || null })}
        />
      </Field>
      <Field label="Preferred locations (comma separated)">
        <TagListInput
          values={entry.preferred_locations}
          onChange={(v) => setEntry({ ...entry, preferred_locations: v })}
          placeholder="Melbourne, Sydney"
        />
      </Field>
      <Field label="Notes (optional)">
        <TextInput
          value={entry.notes ?? ""}
          onChange={(v) => setEntry({ ...entry, notes: v || null })}
        />
      </Field>
      <label className="flex items-center gap-2 text-sm text-zinc-300">
        <input
          type="checkbox"
          checked={entry.enabled}
          onChange={(e) => setEntry({ ...entry, enabled: e.target.checked })}
        />
        Enabled
      </label>
      <div className="flex gap-3">
        <PrimaryButton onClick={() => onSave(entry)}>Save</PrimaryButton>
        <SecondaryButton onClick={onCancel}>Cancel</SecondaryButton>
      </div>
    </div>
  );
}

function healthFor(sourceKey: string, health: SourceHealth[]): SourceHealth | undefined {
  return health.find((h) => h.source_key === sourceKey);
}

export default function CompaniesPage() {
  const [entries, setEntries] = useState<CompanyWatchlistEntry[]>([]);
  const [health, setHealth] = useState<SourceHealth[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  async function loadAll() {
    setLoading(true);
    setError(null);
    try {
      const [list, dashboard] = await Promise.all([
        api.listCompanyWatchlist(),
        api.getDiscoveryDashboard(),
      ]);
      setEntries(list);
      setHealth(dashboard.source_health);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional: initial data load on mount
    void loadAll();
  }, []);

  async function handleCreate(entry: CompanyWatchlistEntry) {
    await api.createCompanyWatchlistEntry(entry);
    setAdding(false);
    await loadAll();
  }

  async function handleUpdate(id: string, entry: CompanyWatchlistEntry) {
    await api.updateCompanyWatchlistEntry(id, entry);
    setEditingId(null);
    await loadAll();
  }

  async function handleToggle(entry: CompanyWatchlistEntry) {
    if (!entry.id) return;
    await api.updateCompanyWatchlistEntry(entry.id, { ...entry, enabled: !entry.enabled });
    await loadAll();
  }

  async function handleDelete(id: string) {
    await api.deleteCompanyWatchlistEntry(id);
    await loadAll();
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100">Companies</h1>
        <p className="mt-1 text-sm text-zinc-400">
          Employers watched directly via their ATS - discovery checks these company-scoped feeds
          in addition to broad job-board search.
        </p>
      </div>

      {error && <ErrorBanner message={error} />}
      {loading && <Spinner />}

      {!loading && (
        <Card>
          <SectionHeading
            title="Watchlist"
            subtitle="Priority here boosts analysis order only - it never changes the candidate fit score."
            action={
              !adding && <AddButton label="+ Watch a company" onClick={() => setAdding(true)} />
            }
          />
          {adding && (
            <div className="mb-4">
              <WatchlistEntryForm
                initial={EMPTY_ENTRY}
                onSave={handleCreate}
                onCancel={() => setAdding(false)}
              />
            </div>
          )}
          {entries.length === 0 && !adding ? (
            <EmptyState
              title="No companies watched yet"
              subtitle="Add a company's Lever or Greenhouse identifier to monitor its postings directly."
            />
          ) : (
            <div className="space-y-3">
              {entries.map((entry) => {
                if (editingId === entry.id) {
                  return (
                    <WatchlistEntryForm
                      key={entry.id}
                      initial={entry}
                      onSave={(updated) => entry.id && handleUpdate(entry.id, updated)}
                      onCancel={() => setEditingId(null)}
                    />
                  );
                }
                const sourceKey = `${entry.ats_type}:${entry.ats_identifier}`;
                const entryHealth = healthFor(sourceKey, health);
                return (
                  <div
                    key={entry.id}
                    className="flex items-center justify-between gap-4 rounded-lg border border-zinc-800 px-4 py-3"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-zinc-200">
                        {entry.company_name}{" "}
                        {!entry.enabled && (
                          <span className="text-xs text-zinc-500">(disabled)</span>
                        )}
                      </p>
                      <p className="truncate text-xs text-zinc-500">
                        {entry.ats_type}:{entry.ats_identifier}
                        {entry.preferred_locations.length > 0 &&
                          ` · ${entry.preferred_locations.join(", ")}`}
                      </p>
                      {entryHealth && (
                        <p className="mt-1 text-xs text-zinc-600">
                          Last checked {formatDateTime(entryHealth.last_attempt_at)} ·{" "}
                          {entryHealth.jobs_retrieved_last_run} jobs last run
                        </p>
                      )}
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <CompanyPriorityBadge priority={entry.priority} />
                      {entryHealth && <SourceHealthBadge status={entryHealth.status} />}
                      <SecondaryButton onClick={() => handleToggle(entry)}>
                        {entry.enabled ? "Disable" : "Enable"}
                      </SecondaryButton>
                      <SecondaryButton onClick={() => setEditingId(entry.id ?? null)}>
                        Edit
                      </SecondaryButton>
                      <RemoveButton onClick={() => entry.id && handleDelete(entry.id)} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
