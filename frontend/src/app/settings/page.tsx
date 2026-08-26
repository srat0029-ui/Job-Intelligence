"use client";

import { useEffect, useState } from "react";
import { Card, ErrorBanner, SectionHeading, Spinner } from "@/components/ui";
import { categoryLabel } from "@/lib/format";

interface SettingsInfo {
  environment: string;
  anthropic_model: string;
  anthropic_api_key_configured: boolean;
  llm_max_retries: number;
  scoring_weights: Record<string, number>;
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

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
          V1 is read-only here - secrets are configured server-side via environment variables and
          are never exposed to the browser.
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
                <dd className={info.anthropic_api_key_configured ? "text-emerald-400" : "text-rose-400"}>
                  {info.anthropic_api_key_configured ? "Configured" : "Not configured (using fallback fake provider)"}
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
