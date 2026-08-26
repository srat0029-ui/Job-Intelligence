"use client";

import { AddButton, Field, RemoveButton, TagListInput, TextAreaInput, TextInput } from "@/components/form";
import type {
  Achievement,
  Certification,
  Education,
  Evidence,
  Project,
  Skill,
  WorkExperience,
} from "@/lib/types";

export function SkillsEditor({
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

export function ProjectsEditor({
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

export function EvidenceEditor({
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
            <p className="text-sm font-medium text-zinc-300">
              Evidence {i + 1}{" "}
              {item.source_type && (
                <span className="text-xs text-zinc-500">({item.source_type})</span>
              )}
            </p>
            <RemoveButton onClick={() => onChange(evidence.filter((_, idx) => idx !== i))} />
          </div>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Source type">
                <TextInput
                  value={item.source_type}
                  onChange={(v) => update(i, { source_type: v })}
                  placeholder="project / work_experience / education / cv"
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

export function EducationEditor({
  education,
  onChange,
}: {
  education: Education[];
  onChange: (education: Education[]) => void;
}) {
  function update(i: number, patch: Partial<Education>) {
    onChange(education.map((e, idx) => (idx === i ? { ...e, ...patch } : e)));
  }
  return (
    <div className="space-y-4">
      {education.map((e, i) => (
        <div key={i} className="rounded-lg border border-zinc-800 p-4">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-sm font-medium text-zinc-300">Education {i + 1}</p>
            <RemoveButton onClick={() => onChange(education.filter((_, idx) => idx !== i))} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Institution">
              <TextInput value={e.institution} onChange={(v) => update(i, { institution: v })} />
            </Field>
            <Field label="Qualification">
              <TextInput value={e.qualification} onChange={(v) => update(i, { qualification: v })} />
            </Field>
            <Field label="Field of study">
              <TextInput
                value={e.field_of_study ?? ""}
                onChange={(v) => update(i, { field_of_study: v })}
              />
            </Field>
            <Field label="End date (YYYY-MM-DD)">
              <TextInput value={e.end_date ?? ""} onChange={(v) => update(i, { end_date: v || null })} />
            </Field>
          </div>
          <label className="mt-3 flex items-center gap-2 text-sm text-zinc-300">
            <input
              type="checkbox"
              checked={e.is_current}
              onChange={(ev) => update(i, { is_current: ev.target.checked })}
            />
            Currently studying here
          </label>
        </div>
      ))}
      <AddButton
        label="+ Add education"
        onClick={() =>
          onChange([
            ...education,
            {
              institution: "",
              qualification: "",
              field_of_study: "",
              start_date: null,
              end_date: null,
              is_current: false,
              notes: "",
            },
          ])
        }
      />
    </div>
  );
}

export function WorkHistoryEditor({
  workHistory,
  onChange,
}: {
  workHistory: WorkExperience[];
  onChange: (workHistory: WorkExperience[]) => void;
}) {
  function update(i: number, patch: Partial<WorkExperience>) {
    onChange(workHistory.map((w, idx) => (idx === i ? { ...w, ...patch } : w)));
  }
  return (
    <div className="space-y-4">
      {workHistory.map((w, i) => (
        <div key={i} className="rounded-lg border border-zinc-800 p-4">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-sm font-medium text-zinc-300">Role {i + 1}</p>
            <RemoveButton onClick={() => onChange(workHistory.filter((_, idx) => idx !== i))} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Company">
              <TextInput value={w.company} onChange={(v) => update(i, { company: v })} />
            </Field>
            <Field label="Title">
              <TextInput value={w.title} onChange={(v) => update(i, { title: v })} />
            </Field>
          </div>
          <div className="mt-3">
            <Field label="Summary">
              <TextAreaInput
                value={w.summary ?? ""}
                onChange={(v) => update(i, { summary: v })}
                rows={2}
              />
            </Field>
          </div>
          <div className="mt-3">
            <Field label="Technologies (comma separated)">
              <TagListInput
                values={w.technologies}
                onChange={(v) => update(i, { technologies: v })}
              />
            </Field>
          </div>
          <label className="mt-3 flex items-center gap-2 text-sm text-zinc-300">
            <input
              type="checkbox"
              checked={w.is_current}
              onChange={(ev) => update(i, { is_current: ev.target.checked })}
            />
            Current role
          </label>
        </div>
      ))}
      <AddButton
        label="+ Add role"
        onClick={() =>
          onChange([
            ...workHistory,
            {
              company: "",
              title: "",
              start_date: null,
              end_date: null,
              is_current: false,
              summary: "",
              technologies: [],
            },
          ])
        }
      />
    </div>
  );
}

export function AchievementsEditor({
  achievements,
  onChange,
}: {
  achievements: Achievement[];
  onChange: (achievements: Achievement[]) => void;
}) {
  function update(i: number, patch: Partial<Achievement>) {
    onChange(achievements.map((a, idx) => (idx === i ? { ...a, ...patch } : a)));
  }
  return (
    <div className="space-y-3">
      {achievements.map((a, i) => (
        <div key={i} className="flex items-end gap-3">
          <div className="flex-1">
            <Field label="Title">
              <TextInput value={a.title} onChange={(v) => update(i, { title: v })} />
            </Field>
          </div>
          <div className="flex-1">
            <Field label="Description">
              <TextInput
                value={a.description ?? ""}
                onChange={(v) => update(i, { description: v })}
              />
            </Field>
          </div>
          <RemoveButton onClick={() => onChange(achievements.filter((_, idx) => idx !== i))} />
        </div>
      ))}
      <AddButton
        label="+ Add achievement"
        onClick={() => onChange([...achievements, { title: "", description: "", date: null }])}
      />
    </div>
  );
}

export function CertificationsEditor({
  certifications,
  onChange,
}: {
  certifications: Certification[];
  onChange: (certifications: Certification[]) => void;
}) {
  function update(i: number, patch: Partial<Certification>) {
    onChange(certifications.map((c, idx) => (idx === i ? { ...c, ...patch } : c)));
  }
  return (
    <div className="space-y-3">
      {certifications.map((c, i) => (
        <div key={i} className="flex items-end gap-3">
          <div className="flex-1">
            <Field label="Name">
              <TextInput value={c.name} onChange={(v) => update(i, { name: v })} />
            </Field>
          </div>
          <div className="flex-1">
            <Field label="Issuer">
              <TextInput value={c.issuer ?? ""} onChange={(v) => update(i, { issuer: v })} />
            </Field>
          </div>
          <RemoveButton onClick={() => onChange(certifications.filter((_, idx) => idx !== i))} />
        </div>
      ))}
      <AddButton
        label="+ Add certification"
        onClick={() =>
          onChange([...certifications, { name: "", issuer: "", date: null, credential_url: "" }])
        }
      />
    </div>
  );
}
