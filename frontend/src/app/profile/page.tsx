"use client";

import { useEffect, useRef, useState } from "react";
import { Field, TagListInput, TextAreaInput, TextInput } from "@/components/form";
import {
  AchievementsEditor,
  CertificationsEditor,
  EducationEditor,
  EvidenceEditor,
  ProjectsEditor,
  SkillsEditor,
  WorkHistoryEditor,
} from "@/components/profile-editors";
import {
  Card,
  ErrorBanner,
  PrimaryButton,
  SecondaryButton,
  SectionHeading,
  Spinner,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import type { Candidate } from "@/lib/types";

const EMPTY_CANDIDATE: Candidate = {
  name: "",
  email: "",
  summary: "",
  strengths: [],
  education: [],
  work_history: [],
  skills: [],
  projects: [],
  achievements: [],
  certifications: [],
  evidence: [],
  preferences: {
    preferred_job_categories: [],
    preferred_locations: [],
    work_rights: [],
    salary_expectation_min: null,
    salary_expectation_max: null,
    salary_currency: "AUD",
    remote_preference: "",
    preferred_technologies: [],
    excluded_job_types: [],
  },
};

function CvImportPanel({
  candidate,
  onMerge,
}: {
  candidate: Candidate;
  onMerge: (patch: Partial<Candidate>) => void;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [proposal, setProposal] = useState<Candidate | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    setProposal(null);
    try {
      const parsed = await api.parseCv(file);
      setProposal(parsed);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to parse CV");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  function addCategory<K extends keyof Candidate>(key: K) {
    if (!proposal) return;
    const existing = candidate[key] as unknown as unknown[];
    const incoming = proposal[key] as unknown as unknown[];
    onMerge({ [key]: [...existing, ...incoming] } as Partial<Candidate>);
  }

  function categoryRow(label: string, key: keyof Candidate) {
    if (!proposal) return null;
    const items = proposal[key] as unknown as unknown[];
    if (!items || items.length === 0) return null;
    return (
      <div className="flex items-center justify-between rounded-lg border border-zinc-800 px-4 py-2.5">
        <span className="text-sm text-zinc-300">
          {label}: <span className="text-zinc-500">{items.length} found</span>
        </span>
        <SecondaryButton onClick={() => addCategory(key)}>Add to profile</SecondaryButton>
      </div>
    );
  }

  return (
    <Card>
      <SectionHeading
        title="Import from CV"
        subtitle="Upload a PDF resume - nothing is saved to your profile until you review and add it below, then hit Save profile."
      />
      <div className="flex items-center gap-3">
        <input
          ref={fileInputRef}
          type="file"
          accept="application/pdf"
          onChange={handleFileChange}
          disabled={uploading}
          className="text-sm text-zinc-400 file:mr-3 file:rounded-lg file:border-0 file:bg-indigo-600 file:px-3 file:py-2 file:text-sm file:font-medium file:text-white hover:file:bg-indigo-500"
        />
        {uploading && <span className="text-sm text-zinc-500">Parsing...</span>}
      </div>

      {error && (
        <div className="mt-3">
          <ErrorBanner message={error} />
        </div>
      )}

      {proposal && (
        <div className="mt-4 space-y-2">
          <p className="text-sm text-zinc-400">
            Found for <span className="text-zinc-200">{proposal.name || "unnamed candidate"}</span>
            . Review and add each category you want - existing profile data is never overwritten
            automatically.
          </p>
          {categoryRow("Education", "education")}
          {categoryRow("Work history", "work_history")}
          {categoryRow("Projects", "projects")}
          {categoryRow("Skills", "skills")}
          {categoryRow("Achievements", "achievements")}
          {categoryRow("Certifications", "certifications")}
          {categoryRow("Evidence", "evidence")}
        </div>
      )}
    </Card>
  );
}

export default function ProfilePage() {
  const [candidate, setCandidate] = useState<Candidate>(EMPTY_CANDIDATE);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api
      .getCandidate()
      .then((c) => c && setCandidate(c))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const result = await api.saveCandidate(candidate);
      setCandidate(result);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save profile");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <Spinner />;

  return (
    <div className="space-y-6 pb-16">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">Candidate Profile</h1>
          <p className="mt-1 text-sm text-zinc-400">
            This data drives every fit score. Edit it here, import from a CV below, or replace{" "}
            <code className="text-zinc-500">backend/app/seed/candidate_seed.json</code> and
            re-run the seed script for a bulk update.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {saved && <span className="text-sm text-emerald-400">Saved</span>}
          <PrimaryButton onClick={handleSave} disabled={saving}>
            {saving ? "Saving..." : "Save profile"}
          </PrimaryButton>
        </div>
      </div>

      {error && <ErrorBanner message={error} />}

      <CvImportPanel
        candidate={candidate}
        onMerge={(patch) => setCandidate({ ...candidate, ...patch })}
      />

      <Card>
        <SectionHeading title="Basics" />
        <div className="grid grid-cols-2 gap-4">
          <Field label="Name">
            <TextInput
              value={candidate.name}
              onChange={(v) => setCandidate({ ...candidate, name: v })}
            />
          </Field>
          <Field label="Email">
            <TextInput
              value={candidate.email ?? ""}
              onChange={(v) => setCandidate({ ...candidate, email: v })}
            />
          </Field>
        </div>
        <div className="mt-4">
          <Field label="Summary">
            <TextAreaInput
              value={candidate.summary ?? ""}
              onChange={(v) => setCandidate({ ...candidate, summary: v })}
            />
          </Field>
        </div>
        <div className="mt-4">
          <Field label="Strengths (comma separated)">
            <TagListInput
              values={candidate.strengths}
              onChange={(v) => setCandidate({ ...candidate, strengths: v })}
            />
          </Field>
        </div>
      </Card>

      <Card>
        <SectionHeading title="Education" />
        <EducationEditor
          education={candidate.education}
          onChange={(education) => setCandidate({ ...candidate, education })}
        />
      </Card>

      <Card>
        <SectionHeading title="Work history" />
        <WorkHistoryEditor
          workHistory={candidate.work_history}
          onChange={(work_history) => setCandidate({ ...candidate, work_history })}
        />
      </Card>

      <Card>
        <SectionHeading title="Skills" />
        <SkillsEditor
          skills={candidate.skills}
          onChange={(skills) => setCandidate({ ...candidate, skills })}
        />
      </Card>

      <Card>
        <SectionHeading title="Projects" />
        <ProjectsEditor
          projects={candidate.projects}
          onChange={(projects) => setCandidate({ ...candidate, projects })}
        />
      </Card>

      <Card>
        <SectionHeading title="Achievements" />
        <AchievementsEditor
          achievements={candidate.achievements}
          onChange={(achievements) => setCandidate({ ...candidate, achievements })}
        />
      </Card>

      <Card>
        <SectionHeading title="Certifications" />
        <CertificationsEditor
          certifications={candidate.certifications}
          onChange={(certifications) => setCandidate({ ...candidate, certifications })}
        />
      </Card>

      <Card>
        <SectionHeading title="Evidence" />
        <EvidenceEditor
          evidence={candidate.evidence}
          onChange={(evidence) => setCandidate({ ...candidate, evidence })}
        />
      </Card>

      <Card>
        <SectionHeading title="Preferences" />
        <div className="grid grid-cols-2 gap-4">
          <Field label="Preferred job categories (comma separated)">
            <TagListInput
              values={candidate.preferences.preferred_job_categories}
              onChange={(v) =>
                setCandidate({
                  ...candidate,
                  preferences: { ...candidate.preferences, preferred_job_categories: v },
                })
              }
            />
          </Field>
          <Field label="Preferred locations (comma separated)">
            <TagListInput
              values={candidate.preferences.preferred_locations}
              onChange={(v) =>
                setCandidate({
                  ...candidate,
                  preferences: { ...candidate.preferences, preferred_locations: v },
                })
              }
            />
          </Field>
          <Field label="Preferred technologies/domains (comma separated)">
            <TagListInput
              values={candidate.preferences.preferred_technologies}
              onChange={(v) =>
                setCandidate({
                  ...candidate,
                  preferences: { ...candidate.preferences, preferred_technologies: v },
                })
              }
            />
          </Field>
          <Field label="Excluded job types (comma separated)">
            <TagListInput
              values={candidate.preferences.excluded_job_types}
              onChange={(v) =>
                setCandidate({
                  ...candidate,
                  preferences: { ...candidate.preferences, excluded_job_types: v },
                })
              }
              placeholder="sales, recruitment"
            />
          </Field>
          <Field label="Work rights (comma separated)">
            <TagListInput
              values={candidate.preferences.work_rights}
              onChange={(v) =>
                setCandidate({
                  ...candidate,
                  preferences: { ...candidate.preferences, work_rights: v },
                })
              }
            />
          </Field>
          <Field label="Remote preference">
            <TextInput
              value={candidate.preferences.remote_preference ?? ""}
              onChange={(v) =>
                setCandidate({
                  ...candidate,
                  preferences: { ...candidate.preferences, remote_preference: v },
                })
              }
              placeholder="remote / hybrid / onsite"
            />
          </Field>
          <Field label="Salary min">
            <TextInput
              value={candidate.preferences.salary_expectation_min?.toString() ?? ""}
              onChange={(v) =>
                setCandidate({
                  ...candidate,
                  preferences: {
                    ...candidate.preferences,
                    salary_expectation_min: v ? Number(v) : null,
                  },
                })
              }
            />
          </Field>
          <Field label="Salary max">
            <TextInput
              value={candidate.preferences.salary_expectation_max?.toString() ?? ""}
              onChange={(v) =>
                setCandidate({
                  ...candidate,
                  preferences: {
                    ...candidate.preferences,
                    salary_expectation_max: v ? Number(v) : null,
                  },
                })
              }
            />
          </Field>
        </div>
      </Card>
    </div>
  );
}
