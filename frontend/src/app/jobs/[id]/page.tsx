"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ApplicationStatusSelector } from "@/components/ApplicationStatusSelector";
import { RecommendationBadge, TierBadge } from "@/components/RecommendationBadge";
import { ScoreBar } from "@/components/ScoreBar";
import {
  Card,
  ErrorBanner,
  PrimaryButton,
  SectionHeading,
  Spinner,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { categoryLabel, formatDate, scoreColorClass } from "@/lib/format";
import type { FitScore, Job, JobAnalysis, RequirementMatch } from "@/lib/types";

function ScoreSummary({ fitScore, onReanalyze, analyzing }: {
  fitScore: FitScore;
  onReanalyze: () => void;
  analyzing: boolean;
}) {
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-5">
          <div className={`text-5xl font-bold ${scoreColorClass(fitScore.overall_score)}`}>
            {fitScore.overall_score.toFixed(0)}
          </div>
          <div>
            <RecommendationBadge recommendation={fitScore.recommendation} />
            <p className="mt-2 max-w-xl text-sm text-zinc-400">{fitScore.reasoning}</p>
          </div>
        </div>
        <PrimaryButton onClick={onReanalyze} disabled={analyzing}>
          {analyzing ? "Analyzing..." : "Re-run analysis"}
        </PrimaryButton>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <ScoreBar label="Technical fit" score={fitScore.technical_fit.raw_score} />
        <ScoreBar label="Project relevance" score={fitScore.project_relevance_fit.raw_score} />
        <ScoreBar label="Experience fit" score={fitScore.experience_fit.raw_score} />
        <ScoreBar label="Domain fit" score={fitScore.domain_fit.raw_score} />
        <ScoreBar label="Education fit" score={fitScore.education_fit.raw_score} />
        <ScoreBar label="Location fit" score={fitScore.location_fit.raw_score} />
        <ScoreBar label="Work rights fit" score={fitScore.work_rights_fit.raw_score} />
      </div>
    </Card>
  );
}

function RequirementRow({ match }: { match: RequirementMatch }) {
  return (
    <tr className="border-b border-zinc-800/60 last:border-0">
      <td className="py-2.5 pr-4 align-top">
        <p className="text-sm font-medium text-zinc-200">{match.requirement_name}</p>
        <p className="text-xs text-zinc-500">
          {match.importance === "required" ? "Required" : "Preferred"}
        </p>
      </td>
      <td className="py-2.5 pr-4 align-top">
        <TierBadge tier={match.tier} />
      </td>
      <td className="py-2.5 pr-4 align-top text-sm text-zinc-400">{match.evidence_summary}</td>
      <td className="py-2.5 align-top text-right text-xs text-zinc-500">
        {match.is_gap ? (
          <span className="font-medium text-rose-400">Gap</span>
        ) : (
          <span className="text-emerald-500">OK</span>
        )}
      </td>
    </tr>
  );
}

function RequirementsBreakdown({ analysis }: { analysis: JobAnalysis }) {
  const byCategory = new Map<string, RequirementMatch[]>();
  for (const match of analysis.match_result.matches) {
    const list = byCategory.get(match.category) ?? [];
    list.push(match);
    byCategory.set(match.category, list);
  }

  return (
    <Card>
      <SectionHeading
        title="Requirement-by-requirement analysis"
        subtitle="Grouped by category, required items first"
      />
      <div className="space-y-6">
        {Array.from(byCategory.entries()).map(([category, matches]) => (
          <div key={category}>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              {categoryLabel(category)}
            </h3>
            <table className="w-full">
              <tbody>
                {matches
                  .slice()
                  .sort((a, b) => (a.importance === b.importance ? 0 : a.importance === "required" ? -1 : 1))
                  .map((m) => (
                    <RequirementRow key={m.requirement_name} match={m} />
                  ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>
    </Card>
  );
}

function ExtractedJobPanel({ analysis }: { analysis: JobAnalysis }) {
  const ej = analysis.extracted_job;
  return (
    <Card>
      <SectionHeading title="Extracted job information" />
      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-xs text-zinc-500">Employment type</dt>
          <dd className="text-zinc-200">{categoryLabel(ej.employment_type)}</dd>
        </div>
        <div>
          <dt className="text-xs text-zinc-500">Seniority</dt>
          <dd className="text-zinc-200">{categoryLabel(ej.seniority)}</dd>
        </div>
        <div>
          <dt className="text-xs text-zinc-500">Role category</dt>
          <dd className="text-zinc-200">{ej.role_category ?? "-"}</dd>
        </div>
        {ej.salary && (ej.salary.min_amount || ej.salary.max_amount) && (
          <div>
            <dt className="text-xs text-zinc-500">Salary</dt>
            <dd className="text-zinc-200">
              {ej.salary.min_amount ?? "?"}-{ej.salary.max_amount ?? "?"} {ej.salary.currency ?? ""}
              {ej.salary.period ? ` / ${ej.salary.period}` : ""}
            </dd>
          </div>
        )}
      </dl>

      {ej.responsibilities.length > 0 && (
        <div className="mt-4">
          <p className="mb-1 text-xs text-zinc-500">Responsibilities</p>
          <ul className="list-inside list-disc space-y-1 text-sm text-zinc-300">
            {ej.responsibilities.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}

      {ej.extraction_summary && (
        <p className="mt-4 rounded-lg bg-zinc-800/50 px-3 py-2 text-sm text-zinc-400">
          {ej.extraction_summary}
        </p>
      )}
    </Card>
  );
}

export default function JobDetailPage() {
  const params = useParams<{ id: string }>();
  const jobId = params.id;

  const [job, setJob] = useState<Job | null>(null);
  const [analysis, setAnalysis] = useState<JobAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showRaw, setShowRaw] = useState(false);

  useEffect(() => {
    if (!jobId) return;
    Promise.all([api.getJob(jobId), api.getLatestAnalysis(jobId)])
      .then(([j, a]) => {
        setJob(j);
        setAnalysis(a);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load job"))
      .finally(() => setLoading(false));
  }, [jobId]);

  async function runAnalysis() {
    if (!jobId) return;
    setAnalyzing(true);
    setError(null);
    try {
      const result = await api.analyzeJob(jobId);
      setAnalysis(result);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setError(
          "No candidate profile exists yet. Seed or create one on the Profile page before analysing jobs."
        );
      } else {
        setError(e instanceof Error ? e.message : "Analysis failed");
      }
    } finally {
      setAnalyzing(false);
    }
  }

  if (loading) return <Spinner />;
  if (!job) return <ErrorBanner message={error ?? "Job not found"} />;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">{job.title}</h1>
          <p className="mt-1 text-sm text-zinc-400">
            {job.company}
            {job.location ? ` · ${job.location}` : ""} · Added {formatDate(job.created_at)}
          </p>
          {job.source_url && (
            <a
              href={job.source_url}
              target="_blank"
              rel="noreferrer"
              className="mt-1 inline-block text-sm text-indigo-400 hover:underline"
            >
              View original posting ↗
            </a>
          )}
        </div>
        <ApplicationStatusSelector
          jobId={job.id}
          status={job.application_status}
          onChange={(status) => setJob({ ...job, application_status: status })}
        />
      </div>

      {error && <ErrorBanner message={error} />}

      {!analysis && (
        <Card>
          <SectionHeading
            title="Not analysed yet"
            subtitle="Run the AI extraction + matching pipeline to get a fit score."
          />
          <PrimaryButton onClick={runAnalysis} disabled={analyzing}>
            {analyzing ? "Analyzing..." : "Run analysis"}
          </PrimaryButton>
        </Card>
      )}

      {analysis && (
        <>
          <ScoreSummary
            fitScore={analysis.fit_score}
            onReanalyze={runAnalysis}
            analyzing={analyzing}
          />
          <ExtractedJobPanel analysis={analysis} />
          <RequirementsBreakdown analysis={analysis} />
        </>
      )}

      <Card>
        <button
          onClick={() => setShowRaw(!showRaw)}
          className="text-sm font-medium text-zinc-400 hover:text-zinc-200"
        >
          {showRaw ? "Hide" : "Show"} original job description
        </button>
        {showRaw && (
          <p className="mt-3 whitespace-pre-wrap text-sm text-zinc-400">{job.raw_description}</p>
        )}
      </Card>
    </div>
  );
}
