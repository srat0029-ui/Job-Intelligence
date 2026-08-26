"use client";

import { useEffect, useState } from "react";
import {
  AddButton,
  Field,
  RemoveButton,
  TagListInput,
  TextAreaInput,
  TextInput,
} from "@/components/form";
import { Card, ErrorBanner, PrimaryButton, SectionHeading, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import type { Candidate, Evidence, Project, Skill } from "@/lib/types";

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
  evidence: [],
  preferences: {
    preferred_job_categories: [],
    preferred_locations: [],
    work_rights: [],
    salary_expectation_min: null,
    salary_expectation_max: null,
    salary_currency: "AUD",
    remote_preference: "",
  },
};

function SkillsEditor({
  skills,
  onChange,
}: {
  skills: Skill[];
  onChange: (skills: Skill[]) => void;
}) {
  function update(i: number, patch: Partial<Skill>) {
    onChange(skills.map((s, idx) => (idx === i ? { ...s, ...patch } : s)));
  }
  return (
    <div className="space-y-3">
      {skills.map((skill, i) => (
        <div key={i} className="flex items-end gap-3">
          <div className="flex-1">
            <Field label="Skill name">
              <TextInput value={skill.name} onChange={(v) => update(i, { name: v })} />
            </Field>
          </div>
          <div className="w-40">
            <Field label="Category">
              <TextInput
                value={skill.category ?? ""}
                onChange={(v) => update(i, { category: v })}
                placeholder="language / tool / domain"
              />
            </Field>
          </div>
          <div className="w-36">
            <Field label="Proficiency">
              <TextInput
                value={skill.proficiency ?? ""}
                onChange={(v) => update(i, { proficiency: v })}
                placeholder="proficient"
              />
            </Field>
          </div>
          <RemoveButton onClick={() => onChange(skills.filter((_, idx) => idx !== i))} />
        </div>
      ))}
      <AddButton
        label="+ Add skill"
        onClick={() =>
          onChange([...skills, { name: "", category: "", aliases: [], proficiency: "" }])
        }
      />
    </div>
  );
}

function ProjectsEditor({
  projects,
  onChange,
}: {
  projects: Project[];
  onChange: (projects: Project[]) => void;
}) {
  function update(i: number, patch: Partial<Project>) {
    onChange(projects.map((p, idx) => (idx === i ? { ...p, ...patch } : p)));
  }
  return (
    <div className="space-y-5">
      {projects.map((project, i) => (
        <div key={i} className="rounded-lg border border-zinc-800 p-4">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-sm font-medium text-zinc-300">Project {i + 1}</p>
            <RemoveButton onClick={() => onChange(projects.filter((_, idx) => idx !== i))} />
          </div>
          <div className="space-y-3">
            <Field label="Name">
              <TextInput value={project.name} onChange={(v) => update(i, { name: v })} />
            </Field>
            <Field label="Description">
              <TextAreaInput
                value={project.description}
                onChange={(v) => update(i, { description: v })}
              />
            </Field>
            <Field label="Technologies (comma separated)">
              <TagListInput
                values={project.technologies}
                onChange={(v) => update(i, { technologies: v })}
              />
            </Field>
            <Field label="GitHub URL">
              <TextInput
                value={project.github_url ?? ""}
                onChange={(v) => update(i, { github_url: v })}
              />
            </Field>
            <Field label="Highlights (comma separated - each becomes a bullet of evidence)">
              <TagListInput
                values={project.highlights}
                onChange={(v) => update(i, { highlights: v })}
              />
            </Field>
          </div>
        </div>
      ))}
      <AddButton
        label="+ Add project"
        onClick={() =>
          onChange([
            ...projects,
            { name: "", description: "", technologies: [], github_url: "", highlights: [] },
          ])
        }
      />
    </div>
  );
}

function EvidenceEditor({
  evidence,
  onChange,
}: {
  evidence: Evidence[];
  onChange: (evidence: Evidence[]) => void;
}) {
  function update(i: number, patch: Partial<Evidence>) {
    onChange(evidence.map((e, idx) => (idx === i ? { ...e, ...patch } : e)));
  }
  return (
    <div className="space-y-4">
      <p className="text-sm text-zinc-400">
        Evidence is what the matching engine cites when it claims you have a skill - every
        positive match traces back to one of these statements.
      </p>
      {evidence.map((item, i) => (
        <div key={i} className="rounded-lg border border-zinc-800 p-4">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-sm font-medium text-zinc-300">Evidence {i + 1}</p>
            <RemoveButton onClick={() => onChange(evidence.filter((_, idx) => idx !== i))} />
          </div>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Source type">
                <TextInput
                  value={item.source_type}
                  onChange={(v) => update(i, { source_type: v })}
                  placeholder="project / work_experience / education"
                />
              </Field>
              <Field label="Source label">
                <TextInput
                  value={item.source_label}
                  onChange={(v) => update(i, { source_label: v })}
                  placeholder="e.g. AFL Pricing Engine"
                />
              </Field>
            </div>
            <Field label="Statement">
              <TextAreaInput
                value={item.statement}
                onChange={(v) => update(i, { statement: v })}
                rows={2}
              />
            </Field>
            <Field label="Skill tags (comma separated)">
              <TagListInput
                values={item.skill_tags}
                onChange={(v) => update(i, { skill_tags: v })}
              />
            </Field>
          </div>
        </div>
      ))}
      <AddButton
        label="+ Add evidence"
        onClick={() =>
          onChange([
            ...evidence,
            { source_type: "project", source_label: "", statement: "", skill_tags: [] },
          ])
        }
      />
    </div>
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
            This data drives every fit score. Edit it here, or replace{" "}
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
