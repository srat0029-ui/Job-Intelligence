"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  PriorityBadge,
  RecommendationBadge,
  ReviewVerdictBadge,
  SourceQualityBadge,
  VerificationStatusBadge,
} from "@/components/RecommendationBadge";
import { Field, TextAreaInput, TextInput } from "@/components/form";
import {
  Card,
  EmptyState,
  ErrorBanner,
  PrimaryButton,
  SectionHeading,
  Spinner,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import {
  APPLICATION_STATUS_LABEL,
  QUESTION_TYPE_LABEL,
  formatDateTime,
  scoreColorClass,
} from "@/lib/format";
import type {
  Candidate,
  ApplicationQuestionResponse,
  ApplicationStrategy,
  ApplicationWorkspace,
  CompanyResearchBundle,
  CoverLetter,
  CVTailoringBatch,
  ResearchSourceType,
  WorkspaceOverview,
} from "@/lib/types";

type TabKey = "overview" | "research" | "strategy" | "cv" | "questions" | "cover-letter";

const TABS: { key: TabKey; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "research", label: "Research" },
  { key: "strategy", label: "Strategy" },
  { key: "cv", label: "CV" },
  { key: "questions", label: "Questions" },
  { key: "cover-letter", label: "Cover Letter" },
];

function evidenceLabelResolver(candidate: Candidate | null) {
  return (evidenceId: string) =>
    candidate?.evidence.find((e) => e.id === evidenceId)?.source_label ?? evidenceId;
}

// --- Overview ---

function OverviewTab({ overview }: { overview: WorkspaceOverview }) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Card>
          <p className="text-xs text-zinc-500">Fit score</p>
          <p
            className={`text-2xl font-bold ${
              overview.overall_score != null ? scoreColorClass(overview.overall_score) : "text-zinc-500"
            }`}
          >
            {overview.overall_score != null ? overview.overall_score.toFixed(0) : "-"}
          </p>
        </Card>
        <Card>
          <p className="text-xs text-zinc-500">Recommendation</p>
          {overview.recommendation ? (
            <div className="mt-1">
              <RecommendationBadge
                recommendation={overview.recommendation as "strong_apply" | "apply" | "stretch" | "low_priority"}
              />
            </div>
          ) : (
            <p className="mt-1 text-sm text-zinc-500">-</p>
          )}
        </Card>
        <Card>
          <p className="text-xs text-zinc-500">Application status</p>
          <p className="mt-1 text-sm text-zinc-200">
            {overview.application_status
              ? APPLICATION_STATUS_LABEL[
                  overview.application_status as keyof typeof APPLICATION_STATUS_LABEL
                ]
              : "Not started"}
          </p>
        </Card>
        <Card>
          <p className="text-xs text-zinc-500">Research</p>
          <p className="mt-1 text-sm text-zinc-200">
            {overview.research_source_count} source(s), {overview.research_claim_count} claim(s)
          </p>
        </Card>
      </div>

      <Card>
        <SectionHeading title="Preparation status" />
        <div className="grid grid-cols-3 gap-3 text-sm">
          <p className={overview.has_strategy ? "text-emerald-400" : "text-zinc-500"}>
            {overview.has_strategy ? "✓" : "○"} Strategy
          </p>
          <p className={overview.has_cv_tailoring ? "text-emerald-400" : "text-zinc-500"}>
            {overview.has_cv_tailoring ? "✓" : "○"} CV tailoring
          </p>
          <p className={overview.has_cover_letter ? "text-emerald-400" : "text-zinc-500"}>
            {overview.has_cover_letter ? "✓" : "○"} Cover letter
          </p>
        </div>
        <p className="mt-2 text-xs text-zinc-500">{overview.question_count} question(s) answered</p>
      </Card>

      {overview.strongest_evidence_labels.length > 0 && (
        <Card>
          <SectionHeading title="Strongest evidence" />
          <ul className="list-inside list-disc space-y-1 text-sm text-zinc-300">
            {overview.strongest_evidence_labels.map((label) => (
              <li key={label}>{label}</li>
            ))}
          </ul>
        </Card>
      )}

      {overview.main_gaps.length > 0 && (
        <Card>
          <SectionHeading title="Main gaps" />
          <ul className="list-inside list-disc space-y-1 text-sm text-rose-400">
            {overview.main_gaps.map((gap) => (
              <li key={gap}>{gap}</li>
            ))}
          </ul>
        </Card>
      )}

      {overview.brief && (
        <Card>
          <SectionHeading
            title="Application Brief"
            subtitle="Read before applying - every factual claim here traces to stored evidence or research."
          />
          <div className="space-y-4 text-sm">
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                Why this role fits
              </p>
              <ul className="list-inside list-disc space-y-0.5 text-zinc-300">
                {overview.brief.why_this_role_fits.map((line, i) => (
                  <li key={i}>{line}</li>
                ))}
              </ul>
            </div>
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                Best evidence to use
              </p>
              <ol className="list-inside list-decimal space-y-0.5 text-zinc-300">
                {overview.brief.best_evidence_to_use.map((item) => (
                  <li key={item.evidence_id}>{item.label}</li>
                ))}
              </ol>
            </div>
            {overview.brief.key_gaps.length > 0 && (
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                  Key gaps
                </p>
                <ul className="list-inside list-disc space-y-0.5 text-rose-400">
                  {overview.brief.key_gaps.map((gap) => (
                    <li key={gap}>{gap}</li>
                  ))}
                </ul>
              </div>
            )}
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                How to position them
              </p>
              <ul className="list-inside list-disc space-y-0.5 text-zinc-300">
                {overview.brief.how_to_position.map((line, i) => (
                  <li key={i}>{line}</li>
                ))}
              </ul>
            </div>
            {overview.brief.company_talking_points.length > 0 && (
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                  Company talking points
                </p>
                <ul className="list-inside list-disc space-y-0.5 text-zinc-300">
                  {overview.brief.company_talking_points.map((point, i) => (
                    <li key={i}>{point}</li>
                  ))}
                </ul>
              </div>
            )}
            {overview.brief.likely_application_themes.length > 0 && (
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                  Likely application themes
                </p>
                <p className="text-zinc-300">
                  {overview.brief.likely_application_themes.join(", ")}
                </p>
              </div>
            )}
          </div>
        </Card>
      )}
    </div>
  );
}

// --- Research ---

const SOURCE_TYPES: ResearchSourceType[] = [
  "official_website",
  "careers_page",
  "engineering_blog",
  "press_release",
  "news",
  "company_directory",
  "other",
];

function ResearchTab({ workspaceId, onChanged }: { workspaceId: string; onChanged: () => void }) {
  const [bundle, setBundle] = useState<CompanyResearchBundle | null>(null);
  const [url, setUrl] = useState("");
  const [sourceType, setSourceType] = useState<ResearchSourceType>("official_website");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const b = await api.getResearchBundle(workspaceId);
    setBundle(b);
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional: load this tab's data on mount/tab change
    void load();
  }, [workspaceId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleAdd() {
    if (!url.trim()) return;
    setAdding(true);
    setError(null);
    try {
      await api.addResearchSource(workspaceId, { url: url.trim(), sourceType });
      setUrl("");
      await load();
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : e instanceof Error ? e.message : "Failed");
    } finally {
      setAdding(false);
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <SectionHeading
          title="Add a research source"
          subtitle="Fetches the page live and extracts only claims grounded in its actual text."
        />
        {error && <ErrorBanner message={error} />}
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-[280px] flex-1">
            <Field label="URL">
              <TextInput
                value={url}
                onChange={setUrl}
                placeholder="https://company.com/about"
              />
            </Field>
          </div>
          <Field label="Source type">
            <select
              value={sourceType}
              onChange={(e) => setSourceType(e.target.value as ResearchSourceType)}
              className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 focus:border-indigo-500 focus:outline-none"
            >
              {SOURCE_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </Field>
          <PrimaryButton onClick={handleAdd} disabled={adding}>
            {adding ? "Researching..." : "Add & Research"}
          </PrimaryButton>
        </div>
      </Card>

      {bundle && bundle.sources.length === 0 && (
        <EmptyState
          title="No research yet"
          subtitle="Add a URL above (the company's site, careers page, or a news article) to start building grounded facts."
        />
      )}

      {bundle && bundle.sources.length > 0 && (
        <Card>
          <SectionHeading title="Sources" />
          <div className="space-y-2">
            {bundle.sources.map((s) => (
              <div key={s.id} className="rounded-lg border border-zinc-800 px-4 py-2.5 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <a href={s.url} target="_blank" rel="noreferrer" className="text-indigo-400 hover:underline">
                    {s.title || s.domain} ↗
                  </a>
                  <div className="flex items-center gap-2">
                    <SourceQualityBadge tier={s.source_quality} />
                    <span className="text-xs text-zinc-500">
                      {s.fetch_status === "failed" ? "Fetch failed" : formatDateTime(s.retrieved_at)}
                    </span>
                  </div>
                </div>
                {s.error_message && <p className="mt-1 text-xs text-rose-400">{s.error_message}</p>}
              </div>
            ))}
          </div>
        </Card>
      )}

      {bundle && bundle.claims.length > 0 && (
        <Card>
          <SectionHeading
            title="Grounded company facts"
            subtitle="Every claim links to the source excerpt that supports it."
          />
          <div className="space-y-3">
            {bundle.claims.map((c) => (
              <div key={c.id} className="rounded-lg border border-zinc-800 px-4 py-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <p className="text-sm text-zinc-200">{c.claim}</p>
                  <div className="flex shrink-0 items-center gap-2">
                    {c.is_stale && (
                      <span className="text-xs font-medium text-amber-400">Stale source</span>
                    )}
                    <VerificationStatusBadge status={c.verification_status} />
                  </div>
                </div>
                <p className="mt-1 text-xs text-zinc-500">
                  {c.category.replace(/_/g, " ")} · confidence {(c.confidence * 100).toFixed(0)}%
                </p>
                <p className="mt-1 rounded bg-zinc-800/50 px-2 py-1 text-xs text-zinc-400">
                  &ldquo;{c.supporting_excerpt}&rdquo;
                </p>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

// --- Strategy ---

function StrategyTab({
  workspaceId,
  candidate,
  onChanged,
}: {
  workspaceId: string;
  candidate: Candidate | null;
  onChanged: () => void;
}) {
  const [strategy, setStrategy] = useState<ApplicationStrategy | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const evidenceLabel = evidenceLabelResolver(candidate);

  async function load() {
    setLoading(true);
    const s = await api.getLatestStrategy(workspaceId);
    setStrategy(s);
    setLoading(false);
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional: load this tab's data on mount/tab change
    void load();
  }, [workspaceId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleGenerate() {
    setGenerating(true);
    setError(null);
    try {
      const s = await api.generateStrategy(workspaceId);
      setStrategy(s);
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : e instanceof Error ? e.message : "Failed");
    } finally {
      setGenerating(false);
    }
  }

  if (loading) return <Spinner />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-zinc-400">
          {strategy ? `Version ${strategy.meta.version}` : "No strategy generated yet."}
        </p>
        <PrimaryButton onClick={handleGenerate} disabled={generating}>
          {generating ? "Generating..." : strategy ? "Regenerate" : "Generate strategy"}
        </PrimaryButton>
      </div>

      {error && <ErrorBanner message={error} />}

      {!strategy && !generating && (
        <EmptyState
          title="No strategy yet"
          subtitle="Generate one to get positioning, lead evidence, and honest gap framing for this role."
        />
      )}

      {strategy && (
        <>
          <Card>
            <SectionHeading
              title="Positioning"
              action={
                <div className="flex items-center gap-2">
                  {strategy.application_priority && (
                    <PriorityBadge priority={strategy.application_priority as "apply_asap" | "strong_apply" | "apply" | "stretch" | "low_priority"} />
                  )}
                </div>
              }
            />
            <p className="text-sm text-zinc-300">{strategy.positioning}</p>
          </Card>

          <Card>
            <SectionHeading title="Lead evidence" />
            <ol className="list-inside list-decimal space-y-1 text-sm text-zinc-300">
              {strategy.lead_evidence_ids.map((id) => (
                <li key={id}>{evidenceLabel(id)}</li>
              ))}
            </ol>
          </Card>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Card>
              <SectionHeading title="Emphasise" />
              <p className="text-sm text-zinc-300">
                {strategy.skills_to_emphasise.join(", ") || "-"}
              </p>
            </Card>
            <Card>
              <SectionHeading title="De-emphasise" />
              <p className="text-sm text-zinc-300">
                {strategy.skills_to_deemphasise.join(", ") || "-"}
              </p>
            </Card>
          </div>

          {strategy.likely_concerns.length > 0 && (
            <Card>
              <SectionHeading title="Likely concerns and how to address them" />
              <div className="space-y-3">
                {strategy.likely_concerns.map((c, i) => (
                  <div key={i}>
                    <p className="text-sm font-medium text-zinc-200">{c.concern}</p>
                    <p className="text-sm text-zinc-400">{c.response_strategy}</p>
                  </div>
                ))}
              </div>
            </Card>
          )}

          <Card>
            <SectionHeading title="Motivation themes" />
            <p className="text-sm text-zinc-300">{strategy.motivation_themes.join(", ") || "-"}</p>
          </Card>
        </>
      )}
    </div>
  );
}

// --- CV tailoring ---

function CvTab({
  workspaceId,
  candidate,
  onChanged,
}: {
  workspaceId: string;
  candidate: Candidate | null;
  onChanged: () => void;
}) {
  const [batch, setBatch] = useState<CVTailoringBatch | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const evidenceLabel = evidenceLabelResolver(candidate);

  async function load() {
    setLoading(true);
    setBatch(await api.getLatestCvTailoring(workspaceId));
    setLoading(false);
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional: load this tab's data on mount/tab change
    void load();
  }, [workspaceId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleGenerate() {
    setGenerating(true);
    setError(null);
    try {
      const b = await api.generateCvTailoring(workspaceId);
      setBatch(b);
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : e instanceof Error ? e.message : "Failed");
    } finally {
      setGenerating(false);
    }
  }

  if (loading) return <Spinner />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-zinc-400">
          {batch ? `Version ${batch.meta.version}` : "No CV tailoring generated yet."}
        </p>
        <PrimaryButton onClick={handleGenerate} disabled={generating}>
          {generating ? "Generating..." : batch ? "Regenerate" : "Generate CV tailoring"}
        </PrimaryButton>
      </div>

      {error && <ErrorBanner message={error} />}

      {batch && (
        <>
          <Card>
            <SectionHeading
              title="Suggestions"
              action={<ReviewVerdictBadge verdict={(batch.meta.reviewer_result ?? "pass") as "pass" | "pass_with_warnings" | "fail"} />}
            />
            {batch.section_emphasis.length > 0 && (
              <p className="mb-4 text-xs text-zinc-500">
                Suggested section order: {batch.section_emphasis.join(" → ")}
              </p>
            )}
            {batch.meta.reviewer_issues.length > 0 && (
              <div className="mb-4 rounded-lg border border-amber-900/50 bg-amber-950/30 px-3 py-2 text-xs text-amber-300">
                {batch.meta.reviewer_issues.map((issue, i) => (
                  <p key={i}>{issue}</p>
                ))}
              </div>
            )}
            <div className="space-y-4">
              {batch.suggestions
                .slice()
                .sort((a, b) => a.relevance_rank - b.relevance_rank)
                .map((s, i) => (
                  <div key={i} className="rounded-lg border border-zinc-800 p-4">
                    <div className="flex items-center justify-between">
                      <p className="text-xs font-medium text-zinc-500">
                        #{s.relevance_rank} · {s.source_ref_label}
                      </p>
                      <span
                        className={`text-xs font-medium ${
                          s.passed_grounding_check ? "text-emerald-400" : "text-rose-400"
                        }`}
                      >
                        {s.passed_grounding_check ? "Grounded" : "Grounding issue"}
                      </span>
                    </div>
                    <p className="mt-2 text-sm text-zinc-500 line-through">{s.original_text}</p>
                    <p className="mt-1 text-sm text-zinc-100">{s.suggested_text}</p>
                    {s.supporting_evidence_ids.length > 0 && (
                      <p className="mt-2 text-xs text-zinc-500">
                        Evidence: {s.supporting_evidence_ids.map(evidenceLabel).join(", ")}
                      </p>
                    )}
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
        </>
      )}

      {!batch && !generating && (
        <EmptyState
          title="No CV tailoring yet"
          subtitle="Generate suggestions for reordering and rewording your CV for this specific role."
        />
      )}
    </div>
  );
}

// --- Questions ---

function QuestionsTab({ workspaceId }: { workspaceId: string }) {
  const [questions, setQuestions] = useState<ApplicationQuestionResponse[]>([]);
  const [questionText, setQuestionText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setQuestions(await api.listQuestions(workspaceId));
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional: load this tab's data on mount/tab change
    void load();
  }, [workspaceId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleSubmit() {
    if (!questionText.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.submitQuestion(workspaceId, questionText.trim());
      setQuestionText("");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : e instanceof Error ? e.message : "Failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <SectionHeading title="Paste an application question" />
        {error && <ErrorBanner message={error} />}
        <TextAreaInput
          value={questionText}
          onChange={setQuestionText}
          rows={3}
          placeholder="Describe your experience working with artificial intelligence."
        />
        <div className="mt-3">
          <PrimaryButton onClick={handleSubmit} disabled={submitting}>
            {submitting ? "Generating..." : "Generate draft answer"}
          </PrimaryButton>
        </div>
      </Card>

      {questions.length === 0 ? (
        <EmptyState title="No questions answered yet" />
      ) : (
        <div className="space-y-4">
          {questions.map((q) => (
            <Card key={q.id}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <p className="text-sm font-medium text-zinc-200">{q.question_text}</p>
                {!q.answered_deterministically && q.meta.reviewer_result && (
                  <ReviewVerdictBadge
                    verdict={q.meta.reviewer_result}
                  />
                )}
              </div>
              <p className="mt-1 text-xs text-zinc-500">
                {q.classifications.map((c) => QUESTION_TYPE_LABEL[c]).join(", ")}
                {q.answered_deterministically && " · answered from your saved profile data"}
              </p>
              <p className="mt-3 whitespace-pre-wrap text-sm text-zinc-300">{q.response_text}</p>
              {q.meta.reviewer_issues.length > 0 && (
                <div className="mt-3 rounded bg-amber-950/30 px-2 py-1 text-xs text-amber-300">
                  {q.meta.reviewer_issues.map((issue, i) => (
                    <p key={i}>{issue}</p>
                  ))}
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

// --- Cover letter ---

function CoverLetterTab({
  workspaceId,
  candidate,
  onChanged,
}: {
  workspaceId: string;
  candidate: Candidate | null;
  onChanged: () => void;
}) {
  const [letter, setLetter] = useState<CoverLetter | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const evidenceLabel = evidenceLabelResolver(candidate);

  async function load() {
    setLoading(true);
    setLetter(await api.getLatestCoverLetter(workspaceId));
    setLoading(false);
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional: load this tab's data on mount/tab change
    void load();
  }, [workspaceId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleGenerate() {
    setGenerating(true);
    setError(null);
    try {
      const l = await api.generateCoverLetter(workspaceId);
      setLetter(l);
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : e instanceof Error ? e.message : "Failed");
    } finally {
      setGenerating(false);
    }
  }

  if (loading) return <Spinner />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-zinc-400">
          {letter ? `Version ${letter.meta.version}` : "No cover letter generated yet."}
        </p>
        <PrimaryButton onClick={handleGenerate} disabled={generating}>
          {generating ? "Generating..." : letter ? "Regenerate" : "Generate cover letter"}
        </PrimaryButton>
      </div>

      {error && <ErrorBanner message={error} />}

      {!letter && !generating && (
        <EmptyState
          title="No cover letter yet"
          subtitle="Generate a first draft grounded in your strategy, evidence, and company research. Never sent automatically."
        />
      )}

      {letter && (
        <Card>
          <SectionHeading
            title="Draft"
            action={
              letter.meta.reviewer_result && (
                <ReviewVerdictBadge verdict={letter.meta.reviewer_result} />
              )
            }
          />
          {letter.meta.reviewer_issues.length > 0 && (
            <div className="mb-4 rounded-lg border border-amber-900/50 bg-amber-950/30 px-3 py-2 text-xs text-amber-300">
              {letter.meta.reviewer_issues.map((issue, i) => (
                <p key={i}>{issue}</p>
              ))}
            </div>
          )}
          <p className="whitespace-pre-wrap text-sm text-zinc-200">{letter.body}</p>
          {letter.source_evidence_ids.length > 0 && (
            <p className="mt-4 border-t border-zinc-800 pt-3 text-xs text-zinc-500">
              Evidence used: {letter.source_evidence_ids.map(evidenceLabel).join(", ")}
            </p>
          )}
        </Card>
      )}
    </div>
  );
}

export default function ApplicationWorkspacePage() {
  const params = useParams<{ id: string }>();
  const jobId = params.id;

  const [workspace, setWorkspace] = useState<ApplicationWorkspace | null>(null);
  const [overview, setOverview] = useState<WorkspaceOverview | null>(null);
  const [candidate, setCandidate] = useState<Candidate | null>(null);
  const [tab, setTab] = useState<TabKey>("overview");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) return;
    (async () => {
      try {
        const ws = await api.getOrCreateWorkspace(jobId);
        setWorkspace(ws);
        const [ov, cand] = await Promise.all([
          api.getWorkspaceOverview(ws.id),
          api.getCandidate(),
        ]);
        setOverview(ov);
        setCandidate(cand);
      } catch (e) {
        setError(e instanceof ApiError ? e.detail : e instanceof Error ? e.message : "Failed to load");
      } finally {
        setLoading(false);
      }
    })();
  }, [jobId]);

  async function refreshOverview() {
    if (!workspace) return;
    setOverview(await api.getWorkspaceOverview(workspace.id));
  }

  if (loading) return <Spinner />;
  if (error) return <ErrorBanner message={error} />;
  if (!workspace || !overview) return null;

  return (
    <div className="space-y-6">
      <div>
        <Link href={`/jobs/${jobId}`} className="text-xs text-indigo-400 hover:underline">
          ← Back to job
        </Link>
        <h1 className="mt-2 text-2xl font-semibold text-zinc-100">
          Application Workspace · {overview.job.title}
        </h1>
        <p className="mt-1 text-sm text-zinc-400">
          {overview.job.company}
          {overview.job.location ? ` · ${overview.job.location}` : ""}
        </p>
      </div>

      <div className="flex flex-wrap gap-1 border-b border-zinc-800">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`rounded-t-lg px-4 py-2 text-sm font-medium transition ${
              tab === t.key
                ? "border-b-2 border-indigo-500 text-indigo-300"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "overview" && <OverviewTab overview={overview} />}
      {tab === "research" && <ResearchTab workspaceId={workspace.id} onChanged={refreshOverview} />}
      {tab === "strategy" && (
        <StrategyTab workspaceId={workspace.id} candidate={candidate} onChanged={refreshOverview} />
      )}
      {tab === "cv" && (
        <CvTab workspaceId={workspace.id} candidate={candidate} onChanged={refreshOverview} />
      )}
      {tab === "questions" && <QuestionsTab workspaceId={workspace.id} />}
      {tab === "cover-letter" && (
        <CoverLetterTab workspaceId={workspace.id} candidate={candidate} onChanged={refreshOverview} />
      )}
    </div>
  );
}
