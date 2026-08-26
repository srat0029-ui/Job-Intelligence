// Thin fetch wrapper around the FastAPI backend. Deliberately not a heavy
// data-fetching library (no React Query etc.) - this is a single-user tool
// with a handful of endpoints, and a plain typed fetch client is easier to
// read end-to-end than an abstraction layer that would only pay for itself
// at much larger scale.

import type {
  Candidate,
  CreateJobRequest,
  DashboardStats,
  Job,
  JobAnalysis,
  JobListItem,
} from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(`API error ${status}: ${detail}`);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // response body wasn't JSON - fall back to statusText
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

export const api = {
  getCandidate: () => request<Candidate | null>("/api/candidate"),
  saveCandidate: (candidate: Candidate) =>
    request<Candidate>("/api/candidate", { method: "PUT", body: JSON.stringify(candidate) }),

  listJobs: () => request<Job[]>("/api/jobs"),
  getJob: (jobId: string) => request<Job>(`/api/jobs/${jobId}`),
  createJob: (payload: CreateJobRequest) =>
    request<Job>("/api/jobs", { method: "POST", body: JSON.stringify(payload) }),
  analyzeJob: (jobId: string) =>
    request<JobAnalysis>(`/api/jobs/${jobId}/analyze`, { method: "POST" }),
  getLatestAnalysis: (jobId: string) =>
    request<JobAnalysis | null>(`/api/jobs/${jobId}/analysis`),

  getDashboard: () => request<DashboardStats>("/api/dashboard"),
  getPrioritizedJobs: () => request<JobListItem[]>("/api/dashboard/prioritized"),
};
