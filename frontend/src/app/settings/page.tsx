"use client";

import { useEffect, useState } from "react";
import { Field, TextInput } from "@/components/form";
import { Card, ErrorBanner, PrimaryButton, SectionHeading, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { categoryLabel } from "@/lib/format";
import type { AppSettings, CostSummary } from "@/lib/types";

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

  if (!settings) return null;

  return (
    <Card>
      <SectionHeading
        title="AI cost controls"
        subtitle="Governs the automated analysis phase of a discovery run. Manually forcing analysis of one job always bypasses these."
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
