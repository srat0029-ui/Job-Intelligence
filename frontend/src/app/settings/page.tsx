"use client";

import { useEffect, useState } from "react";
import { Field, TextInput } from "@/components/form";
import {
  Card,
  ErrorBanner,
  PrimaryButton,
  SecondaryButton,
  SectionHeading,
  Spinner,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { categoryLabel, formatDateTime } from "@/lib/format";
import type { AppSettings, CommunicationStyle, CostSummary } from "@/lib/types";

interface SettingsInfo {
  environment: string;
  anthropic_model: string;
  anthropic_api_key_configured: boolean;
  llm_max_retries: number;
  scoring_weights: Record<string, number>;
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

function CostControlsCard() {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [cost, setCost] = useState<CostSummary | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runningNow, setRunningNow] = useState(false);
  const [runNowMessage, setRunNowMessage] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.getDiscoverySettings(), api.getCostSummary()])
      .then(([s, c]) => {
        setSettings(s);
        setCost(c);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  }, []);

  async function handleSave() {
    if (!settings) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await api.updateDiscoverySettings(settings);
      setSettings(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  async function handleRunNow() {
    setRunningNow(true);
    setRunNowMessage(null);
    setError(null);
    try {
      const run = await api.runDiscovery();
      setRunNowMessage(
        `Started - ${run.counts.retrieved} retrieved, ${run.counts.new} new, ${run.counts.analysed} analysed.`
      );
      const refreshed = await api.getDiscoverySettings();
      setSettings(refreshed);
    } catch (e) {
      if (e instanceof ApiError) {
        setError(e.detail);
      } else {
        setError(e instanceof Error ? e.message : "Failed to run discovery");
      }
    } finally {
      setRunningNow(false);
    }
  }

  if (!settings) return null;

  return (
    <Card>
      <SectionHeading
        title="AI cost & discovery scheduling controls"
        subtitle="Governs the automated analysis phase and automatic scheduling of discovery runs. Manually forcing analysis of one job always bypasses these."
        action={
          <div className="flex items-center gap-3">
            {saved && <span className="text-sm text-emerald-400">Saved</span>}
            <PrimaryButton onClick={handleSave} disabled={saving}>
              {saving ? "Saving..." : "Save"}
            </PrimaryButton>
          </div>
        }
      />
      {error && <ErrorBanner message={error} />}

      <label className="mb-4 flex items-center gap-2 text-sm text-zinc-300">
        <input
          type="checkbox"
          checked={settings.auto_ai_analysis_enabled}
          onChange={(e) =>
            setSettings({ ...settings, auto_ai_analysis_enabled: e.target.checked })
          }
        />
        Automatically analyse eligible jobs during a discovery run
      </label>

      <div className="grid grid-cols-2 gap-4">
        <Field label="Max AI analyses per discovery run">
          <TextInput
            value={String(settings.max_ai_analyses_per_run)}
            onChange={(v) =>
              setSettings({ ...settings, max_ai_analyses_per_run: Number(v) || 0 })
            }
          />
        </Field>
        <Field label="Daily AI analysis budget (USD, blank = unlimited)">
          <TextInput
            value={settings.daily_ai_analysis_budget_usd?.toString() ?? ""}
            onChange={(v) =>
              setSettings({
                ...settings,
                daily_ai_analysis_budget_usd: v ? Number(v) : null,
              })
            }
          />
        </Field>
      </div>

      {cost && (
        <dl className="mt-5 grid grid-cols-3 gap-4 border-t border-zinc-800 pt-4 text-sm">
          <div>
            <dt className="text-xs text-zinc-500">Spent today</dt>
            <dd className="text-zinc-200">${cost.spent_today_usd.toFixed(4)}</dd>
          </div>
          <div>
            <dt className="text-xs text-zinc-500">Spent all-time</dt>
            <dd className="text-zinc-200">${cost.spent_all_time_usd.toFixed(4)}</dd>
          </div>
          <div>
            <dt className="text-xs text-zinc-500">Daily budget</dt>
            <dd className="text-zinc-200">
              {cost.daily_budget_usd != null ? `$${cost.daily_budget_usd.toFixed(2)}` : "Unlimited"}
            </dd>
          </div>
        </dl>
      )}

      <div className="mt-5 border-t border-zinc-800 pt-4">
        <label className="mb-4 flex items-center gap-2 text-sm text-zinc-300">
          <input
            type="checkbox"
            checked={settings.auto_discovery_enabled}
            onChange={(e) =>
              setSettings({ ...settings, auto_discovery_enabled: e.target.checked })
            }
          />
          Automatically run discovery on a schedule
        </label>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Frequency (hours between runs)">
            <TextInput
              value={String(settings.discovery_frequency_hours)}
              onChange={(v) =>
                setSettings({ ...settings, discovery_frequency_hours: Number(v) || 1 })
              }
            />
          </Field>
          <Field label="Max postings fetched per source per run">
            <TextInput
              value={String(settings.max_postings_per_source_per_run)}
              onChange={(v) =>
                setSettings({ ...settings, max_postings_per_source_per_run: Number(v) || 1 })
              }
            />
          </Field>
        </div>

        <dl className="mt-4 grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="text-xs text-zinc-500">Last scheduled run</dt>
            <dd className="text-zinc-200">{formatDateTime(settings.last_scheduled_run_at)}</dd>
          </div>
          <div>
            <dt className="text-xs text-zinc-500">Next scheduled run</dt>
            <dd className="text-zinc-200">{formatDateTime(settings.next_scheduled_run_at)}</dd>
          </div>
        </dl>

        <div className="mt-4 flex items-center gap-3">
          <SecondaryButton onClick={handleRunNow} disabled={runningNow}>
            {runningNow ? "Running..." : "Run discovery now"}
          </SecondaryButton>
          {runNowMessage && <span className="text-sm text-zinc-400">{runNowMessage}</span>}
        </div>
      </div>
    </Card>
  );
}

const TONE_OPTIONS = ["concise", "natural", "conversational_professional"];

function CommunicationStyleCard() {
  const [style, setStyle] = useState<CommunicationStyle | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getCommunicationStyle()
      .then(setStyle)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  }, []);

  async function handleSave() {
    if (!style) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await api.updateCommunicationStyle(style);
      setStyle(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  if (!style) return null;

  return (
    <Card>
      <SectionHeading
        title="Application writing style"
        subtitle="Shapes HOW generated application material reads (cover letters, CV suggestions, question answers) - it never relaxes grounding rules, which are enforced entirely in code regardless of style."
        action={
          <div className="flex items-center gap-3">
            {saved && <span className="text-sm text-emerald-400">Saved</span>}
            <PrimaryButton onClick={handleSave} disabled={saving}>
              {saving ? "Saving..." : "Save"}
            </PrimaryButton>
          </div>
        }
      />
      {error && <ErrorBanner message={error} />}

      <div className="grid grid-cols-2 gap-4">
        <Field label="Tone">
          <select
            value={style.tone}
            onChange={(e) => setStyle({ ...style, tone: e.target.value })}
            className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none"
          >
            {TONE_OPTIONS.map((t) => (
              <option key={t} value={t}>
                {t.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Region convention">
          <TextInput
            value={style.region_convention}
            onChange={(v) => setStyle({ ...style, region_convention: v })}
          />
        </Field>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2">
        <label className="flex items-center gap-2 text-sm text-zinc-300">
          <input
            type="checkbox"
            checked={style.avoid_buzzwords}
            onChange={(e) => setStyle({ ...style, avoid_buzzwords: e.target.checked })}
          />
          Avoid unnecessary corporate buzzwords
        </label>
        <label className="flex items-center gap-2 text-sm text-zinc-300">
          <input
            type="checkbox"
            checked={style.avoid_exaggerated_claims}
            onChange={(e) => setStyle({ ...style, avoid_exaggerated_claims: e.target.checked })}
          />
          Avoid exaggerated claims
        </label>
        <label className="flex items-center gap-2 text-sm text-zinc-300">
          <input
            type="checkbox"
            checked={style.prefer_specific_examples}
            onChange={(e) => setStyle({ ...style, prefer_specific_examples: e.target.checked })}
          />
          Prefer specific examples
        </label>
        <label className="flex items-center gap-2 text-sm text-zinc-300">
          <input
            type="checkbox"
            checked={style.avoid_em_dashes}
            onChange={(e) => setStyle({ ...style, avoid_em_dashes: e.target.checked })}
          />
          Avoid em dashes
        </label>
      </div>
    </Card>
  );
}

export default function SettingsPage() {
  const [info, setInfo] = useState<SettingsInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/settings`, { cache: "no-store" })
      .then((res) => res.json())
      .then(setInfo)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100">Settings</h1>
        <p className="mt-1 text-sm text-zinc-400">
          Secrets are configured server-side via environment variables and are never exposed to
          the browser. Cost controls below are live and editable.
        </p>
      </div>

      {loading && <Spinner />}
      {error && <ErrorBanner message={error} />}

      {info && (
        <>
          <Card>
            <SectionHeading title="AI provider" />
            <dl className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-3">
              <div>
                <dt className="text-xs text-zinc-500">Environment</dt>
                <dd className="text-zinc-200">{info.environment}</dd>
              </div>
              <div>
                <dt className="text-xs text-zinc-500">Model</dt>
                <dd className="text-zinc-200">{info.anthropic_model}</dd>
              </div>
              <div>
                <dt className="text-xs text-zinc-500">API key</dt>
                <dd
                  className={
                    info.anthropic_api_key_configured ? "text-emerald-400" : "text-rose-400"
                  }
                >
                  {info.anthropic_api_key_configured
                    ? "Configured"
                    : "Not configured (using fallback fake provider)"}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-zinc-500">Max retries</dt>
                <dd className="text-zinc-200">{info.llm_max_retries}</dd>
              </div>
            </dl>
            {!info.anthropic_api_key_configured && (
              <p className="mt-4 rounded-lg bg-amber-950/40 px-3 py-2 text-sm text-amber-300">
                Set <code>ANTHROPIC_API_KEY</code> in <code>backend/.env</code> and restart the
                backend to enable real job extraction and matching.
              </p>
            )}
          </Card>

          <CostControlsCard />

          <CommunicationStyleCard />

          <Card>
            <SectionHeading
              title="Scoring weights"
              subtitle="Fixed, deterministic weights used to combine sub-scores into the overall fit score - edit backend/app/services/scoring_service.py to change these."
            />
            <div className="space-y-2">
              {Object.entries(info.scoring_weights).map(([name, weight]) => (
                <div key={name} className="flex items-center justify-between text-sm">
                  <span className="text-zinc-300">{categoryLabel(name)}</span>
                  <span className="text-zinc-500">{(weight * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
