"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { APPLICATION_STATUS_LABEL, APPLICATION_STATUS_OPTIONS } from "@/lib/format";
import type { ApplicationStatus } from "@/lib/types";

/** Manual-only tracker - selecting a status here just records it, it never
 * submits an application anywhere. See backend
 * app/services/application_status_service.py. */
export function ApplicationStatusSelector({
  jobId,
  status,
  onChange,
}: {
  jobId: string;
  status?: ApplicationStatus | null;
  onChange?: (status: ApplicationStatus) => void;
}) {
  const [saving, setSaving] = useState(false);

  async function handleChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const next = e.target.value as ApplicationStatus;
    setSaving(true);
    try {
      await api.setApplicationStatus(jobId, next);
      onChange?.(next);
    } finally {
      setSaving(false);
    }
  }

  return (
    <select
      value={status ?? ""}
      onChange={handleChange}
      disabled={saving}
      onClick={(e) => e.stopPropagation()}
      className="rounded-lg border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-xs font-medium text-zinc-200 focus:border-indigo-500 focus:outline-none"
    >
      <option value="" disabled>
        Set status...
      </option>
      {APPLICATION_STATUS_OPTIONS.map((opt) => (
        <option key={opt} value={opt}>
          {APPLICATION_STATUS_LABEL[opt]}
        </option>
      ))}
    </select>
  );
}
