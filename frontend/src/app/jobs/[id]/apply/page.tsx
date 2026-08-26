"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ApplicationStatusSelector } from "@/components/ApplicationStatusSelector";
import { ReviewVerdictBadge } from "@/components/RecommendationBadge";
import { Card, ErrorBanner, PrimaryButton, SecondaryButton, SectionHeading, Spinner } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import type { ApplicationPack } from "@/lib/types";

const PREPARING_MESSAGES = [
  "Analysing fit...",
  "Researching the company...",
  "Tailoring your application...",
];

export default function ApplicationPackPage() {
  const params = useParams<{ id: string }>();
  const jobId = params.id;

  const [pack, setPack] = useState<ApplicationPack | null>(null);
  const [loading, setLoading] = useState(true);
  const [regenerating, setRegenerating] = useState(false);
  const [messageIndex, setMessageIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);

  async function load(forceRefresh = false) {
    if (forceRefresh) setRegenerating(true);
    else setLoading(true);
    setError(null);
    try {
      const result = await api.prepareApplication(jobId, { forceRefresh });
      setPack(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : e instanceof Error ? e.message : "Failed");
    } finally {
      setLoading(false);
      setRegenerating(false);
    }
  }

  useEffect(() => {
    if (!jobId) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional: load the pack when the job changes
    void load();
  }, [jobId]);

  useEffect(() => {
    if (!loading && !regenerating) return;
    const interval = setInterval(() => {
      setMessageIndex((i) => (i + 1) % PREPARING_MESSAGES.length);
    }, 1800);
    return () => clearInterval(interval);
  }, [loading, regenerating]);

  if (loading) {
    return (
      <div className="space-y-4">
        <Spinner />
        <p className="text-center text-sm text-zinc-400">
          Preparing application... {PREPARING_MESSAGES[messageIndex]}
        </p>
      </div>
    );
  }

  if (error && !pack) return <ErrorBanner message={error} />;
  if (!pack) return null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link href={`/jobs/${jobId}`} className="text-xs text-indigo-400 hover:underline">
            ← Back to job
          </Link>
          <h1 className="mt-2 text-2xl font-semibold text-zinc-100">
            Application Pack · {pack.job_title}
          </h1>
          <p className="mt-1 text-sm text-zinc-400">{pack.company}</p>
        </div>
        <div className="flex items-center gap-2">
          <ApplicationStatusSelector
            jobId={pack.job_id}
            status={pack.application_status}
            onChange={(next) => setPack({ ...pack, application_status: next })}
          />
          <SecondaryButton onClick={() => load(true)} disabled={regenerating}>
            {regenerating ? "Regenerating..." : "Regenerate"}
          </SecondaryButton>
        </div>
      </div>

      {error && <ErrorBanner message={error} />}

      {pack.original_url && (
        <Card className="flex flex-wrap items-center justify-between gap-3 border-indigo-800/50 bg-indigo-950/20">
          <p className="text-sm text-zinc-300">Ready to apply? Open the original listing.</p>
          <a href={pack.original_url} target="_blank" rel="noreferrer">
            <PrimaryButton>Open Original Application ↗</PrimaryButton>
          </a>
        </Card>
      )}

      <Card>
        <SectionHeading title="Why I fit" />
        <ul className="list-inside list-disc space-y-1 text-sm text-zinc-300">
          {pack.brief.why_this_role_fits.map((line, i) => (
            <li key={i}>{line}</li>
          ))}
        </ul>
      </Card>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Card>
          <SectionHeading title="What to emphasise" />
          <ol className="list-inside list-decimal space-y-1 text-sm text-zinc-300">
            {pack.brief.best_evidence_to_use.map((item) => (
              <li key={item.evidence_id}>{item.label}</li>
            ))}
          </ol>
        </Card>
        {pack.brief.key_gaps.length > 0 && (
          <Card>
            <SectionHeading title="Main gaps" />
            <ul className="list-inside list-disc space-y-1 text-sm text-amber-400">
              {pack.brief.key_gaps.map((gap) => (
                <li key={gap}>{gap}</li>
              ))}
            </ul>
          </Card>
        )}
      </div>

      {pack.brief.how_to_position.length > 0 && (
        <Card>
          <SectionHeading title="How to position yourself" />
          <ul className="list-inside list-disc space-y-1 text-sm text-zinc-300">
            {pack.brief.how_to_position.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
        </Card>
      )}

      {pack.cv_suggestions.length > 0 && (
        <Card>
          <SectionHeading
            title="Tailored CV suggestions"
            action={
              pack.cv_reviewer_result && (
                <ReviewVerdictBadge
                  verdict={pack.cv_reviewer_result as "pass" | "pass_with_warnings" | "fail"}
                />
              )
            }
          />
          <div className="space-y-4">
            {pack.cv_suggestions
              .slice()
              .sort((a, b) => a.relevance_rank - b.relevance_rank)
              .map((s, i) => (
                <div key={i} className="rounded-lg border border-zinc-800 p-3">
                  <p className="text-xs font-medium text-zinc-500">{s.source_ref_label}</p>
                  <p className="mt-1 text-sm text-zinc-500 line-through">{s.original_text}</p>
                  <p className="mt-1 text-sm text-zinc-100">{s.suggested_text}</p>
                  {!s.passed_grounding_check && s.grounding_issues.length > 0 && (
                    <div className="mt-2 rounded bg-rose-950/40 px-2 py-1 text-xs text-rose-300">
                      {s.grounding_issues.map((issue, j) => (
                        <p key={j}>{issue}</p>
                      ))}
                    </div>
                  )}
                </div>
              ))}
          </div>
        </Card>
      )}

      {pack.cover_letter_body && (
        <Card>
          <SectionHeading
            title="Cover letter"
            action={
              pack.cover_letter_reviewer_result && (
                <ReviewVerdictBadge
                  verdict={
                    pack.cover_letter_reviewer_result as "pass" | "pass_with_warnings" | "fail"
                  }
                />
              )
            }
          />
          {pack.cover_letter_reviewer_issues.length > 0 && (
            <div className="mb-3 rounded-lg border border-amber-900/50 bg-amber-950/30 px-3 py-2 text-xs text-amber-300">
              {pack.cover_letter_reviewer_issues.map((issue, i) => (
                <p key={i}>{issue}</p>
              ))}
            </div>
          )}
          <p className="whitespace-pre-wrap text-sm text-zinc-200">{pack.cover_letter_body}</p>
        </Card>
      )}

      {pack.brief.company_talking_points.length > 0 && (
        <Card>
          <SectionHeading title="Company talking points" />
          <ul className="list-inside list-disc space-y-1 text-sm text-zinc-300">
            {pack.brief.company_talking_points.map((point, i) => (
              <li key={i}>{point}</li>
            ))}
          </ul>
        </Card>
      )}

      <p className="text-center text-xs text-zinc-600">
        Want to dig deeper (research sources, application questions, version history)?{" "}
        <Link href={`/jobs/${jobId}/workspace`} className="text-indigo-400 hover:underline">
          Open the full Application Workspace →
        </Link>
      </p>
    </div>
  );
}
