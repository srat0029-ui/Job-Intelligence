// Thin fetch wrapper around the FastAPI backend. Deliberately not a heavy
// data-fetching library (no React Query etc.) - this is a single-user tool
// with a handful of endpoints, and a plain typed fetch client is easier to
// read end-to-end than an abstraction layer that would only pay for itself
// at much larger scale.

import type {
  ApplicationBrief,
  ApplicationPack,
  ApplicationQuestionResponse,
  ApplicationStatus,
  ApplicationStatusEvent,
  ApplicationStrategy,
  ApplicationWorkspace,
  AppSettings,
  AttentionItem,
  Candidate,
  CommunicationStyle,
  CompanyResearchBundle,
  CompanyWatchlistEntry,
  CostSummary,
  CoverLetter,
  CreateJobRequest,
  CVTailoringBatch,
  DashboardStats,
  DiscoveredJob,
  DiscoveredJobStatus,
  DiscoveryDashboardStats,
  DiscoveryRun,
  Job,
  JobAnalysis,
  JobListItem,
  OpportunityItem,
  OpportunityPage,
  ResearchSource,
  ResearchSourceType,
  SearchProfile,
  WorkspaceOverview,
  WorkspaceTrace,
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

async function handleResponse<T>(res: Response): Promise<T> {
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  return handleResponse<T>(res);
}

async function requestForm<T>(path: string, formData: FormData): Promise<T> {
  // No Content-Type header here on purpose - the browser sets the
  // multipart boundary itself; overriding it breaks the upload.
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    body: formData,
    cache: "no-store",
  });
  return handleResponse<T>(res);
}

function query(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export const api = {
  getCandidate: () => request<Candidate | null>("/api/candidate"),
  saveCandidate: (candidate: Candidate) =>
    request<Candidate>("/api/candidate", { method: "PUT", body: JSON.stringify(candidate) }),
  parseCv: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return requestForm<Candidate>("/api/candidate/cv/parse", formData);
  },

  listJobs: () => request<Job[]>("/api/jobs"),
  getJob: (jobId: string) => request<Job>(`/api/jobs/${jobId}`),
  createJob: (payload: CreateJobRequest) =>
    request<Job>("/api/jobs", { method: "POST", body: JSON.stringify(payload) }),
  analyzeJob: (jobId: string) =>
    request<JobAnalysis>(`/api/jobs/${jobId}/analyze`, { method: "POST" }),
  getLatestAnalysis: (jobId: string) =>
    request<JobAnalysis | null>(`/api/jobs/${jobId}/analysis`),
  setApplicationStatus: (jobId: string, status: ApplicationStatus, note?: string) =>
    request<Job>(`/api/jobs/${jobId}/status`, {
      method: "PUT",
      body: JSON.stringify({ status, note }),
    }),
  getApplicationStatusHistory: (jobId: string) =>
    request<ApplicationStatusEvent[]>(`/api/jobs/${jobId}/status/history`),

  getDashboard: () => request<DashboardStats>("/api/dashboard"),
  getPrioritizedJobs: () => request<JobListItem[]>("/api/dashboard/prioritized"),

  // --- Discovery ---
  listSearchProfiles: () => request<SearchProfile[]>("/api/discovery/search-profiles"),
  createSearchProfile: (profile: SearchProfile) =>
    request<SearchProfile>("/api/discovery/search-profiles", {
      method: "POST",
      body: JSON.stringify(profile),
    }),
  updateSearchProfile: (id: string, profile: SearchProfile) =>
    request<SearchProfile>(`/api/discovery/search-profiles/${id}`, {
      method: "PUT",
      body: JSON.stringify(profile),
    }),
  deleteSearchProfile: (id: string) =>
    request<void>(`/api/discovery/search-profiles/${id}`, { method: "DELETE" }),

  runDiscovery: (searchProfileIds?: string[]) =>
    request<DiscoveryRun>("/api/discovery/run", {
      method: "POST",
      body: JSON.stringify({ search_profile_ids: searchProfileIds ?? null }),
    }),
  listDiscoveryRuns: () => request<DiscoveryRun[]>("/api/discovery/runs"),
  getDiscoveryRun: (runId: string) => request<DiscoveryRun>(`/api/discovery/runs/${runId}`),
  getDiscoveryRunJobs: (runId: string) =>
    request<DiscoveredJob[]>(`/api/discovery/runs/${runId}/jobs`),

  listOpportunities: (opts: {
    sortBy?: string;
    order?: "asc" | "desc";
    status?: DiscoveredJobStatus;
    searchProfileId?: string;
    includeRejected?: boolean;
    analysedOnly?: boolean;
    reviewed?: boolean;
    minScore?: number;
    page?: number;
    pageSize?: number;
  } = {}) =>
    request<OpportunityPage>(
      `/api/discovery/opportunities${query({
        sort_by: opts.sortBy,
        order: opts.order,
        status: opts.status,
        search_profile_id: opts.searchProfileId,
        include_rejected: opts.includeRejected,
        analysed_only: opts.analysedOnly,
        reviewed: opts.reviewed,
        min_score: opts.minScore,
        page: opts.page,
        page_size: opts.pageSize,
      })}`
    ),
  markOpportunityReviewed: (discoveredJobId: string) =>
    request<DiscoveredJob>(`/api/discovery/opportunities/${discoveredJobId}/reviewed`, {
      method: "PUT",
    }),
  ignoreOpportunity: (discoveredJobId: string) =>
    request<DiscoveredJob>(`/api/discovery/opportunities/${discoveredJobId}/ignore`, {
      method: "PUT",
    }),
  forceAnalyzeDiscoveredJob: (discoveredJobId: string) =>
    request<OpportunityItem>(`/api/discovery/discovered-jobs/${discoveredJobId}/analyze`, {
      method: "POST",
    }),

  getDiscoverySettings: () => request<AppSettings>("/api/discovery/settings"),
  updateDiscoverySettings: (settings: AppSettings) =>
    request<AppSettings>("/api/discovery/settings", {
      method: "PUT",
      body: JSON.stringify(settings),
    }),
  getCostSummary: () => request<CostSummary>("/api/discovery/cost-summary"),

  // --- Company watchlist ---
  listCompanyWatchlist: () => request<CompanyWatchlistEntry[]>("/api/company-watchlist"),
  createCompanyWatchlistEntry: (entry: CompanyWatchlistEntry) =>
    request<CompanyWatchlistEntry>("/api/company-watchlist", {
      method: "POST",
      body: JSON.stringify(entry),
    }),
  updateCompanyWatchlistEntry: (id: string, entry: CompanyWatchlistEntry) =>
    request<CompanyWatchlistEntry>(`/api/company-watchlist/${id}`, {
      method: "PUT",
      body: JSON.stringify(entry),
    }),
  deleteCompanyWatchlistEntry: (id: string) =>
    request<void>(`/api/company-watchlist/${id}`, { method: "DELETE" }),

  // --- Attention / notifications ---
  listAttentionItems: (opts: { unreadOnly?: boolean; limit?: number } = {}) =>
    request<AttentionItem[]>(
      `/api/attention${query({ unread_only: opts.unreadOnly, limit: opts.limit })}`
    ),
  getUnreadAttentionCount: () =>
    request<{ unread_count: number }>("/api/attention/unread-count"),
  markAttentionItemRead: (id: string) =>
    request<AttentionItem>(`/api/attention/${id}/read`, { method: "PUT" }),

  getDiscoveryDashboard: () => request<DiscoveryDashboardStats>("/api/dashboard/discovery"),

  // --- Application Workspace (Milestone 4A) ---
  getOrCreateWorkspace: (jobId: string) =>
    request<ApplicationWorkspace>(`/api/jobs/${jobId}/workspace`, { method: "POST" }),
  prepareApplication: (jobId: string, opts: { forceRefresh?: boolean } = {}) =>
    request<ApplicationPack>(
      `/api/jobs/${jobId}/prepare-application${query({ force_refresh: opts.forceRefresh })}`,
      { method: "POST" }
    ),
  getWorkspaceOverview: (workspaceId: string) =>
    request<WorkspaceOverview>(`/api/application-workspaces/${workspaceId}`),
  updateWorkspaceNotes: (workspaceId: string, notes: string) =>
    request<ApplicationWorkspace>(`/api/application-workspaces/${workspaceId}/notes`, {
      method: "PUT",
      body: JSON.stringify({ notes }),
    }),
  getApplicationBrief: (workspaceId: string) =>
    request<ApplicationBrief>(`/api/application-workspaces/${workspaceId}/brief`),
  getWorkspaceTrace: (workspaceId: string) =>
    request<WorkspaceTrace>(`/api/application-workspaces/${workspaceId}/trace`),

  addResearchSource: (
    workspaceId: string,
    payload: { url: string; sourceType: ResearchSourceType; forceRefresh?: boolean }
  ) =>
    request<ResearchSource>(`/api/application-workspaces/${workspaceId}/research/sources`, {
      method: "POST",
      body: JSON.stringify({
        url: payload.url,
        source_type: payload.sourceType,
        force_refresh: payload.forceRefresh ?? false,
      }),
    }),
  getResearchBundle: (workspaceId: string) =>
    request<CompanyResearchBundle>(`/api/application-workspaces/${workspaceId}/research`),

  generateStrategy: (workspaceId: string) =>
    request<ApplicationStrategy>(`/api/application-workspaces/${workspaceId}/strategy`, {
      method: "POST",
    }),
  getLatestStrategy: (workspaceId: string) =>
    request<ApplicationStrategy | null>(`/api/application-workspaces/${workspaceId}/strategy`),
  getStrategyHistory: (workspaceId: string) =>
    request<ApplicationStrategy[]>(`/api/application-workspaces/${workspaceId}/strategy/history`),

  generateCvTailoring: (workspaceId: string) =>
    request<CVTailoringBatch>(`/api/application-workspaces/${workspaceId}/cv-tailoring`, {
      method: "POST",
    }),
  getLatestCvTailoring: (workspaceId: string) =>
    request<CVTailoringBatch | null>(`/api/application-workspaces/${workspaceId}/cv-tailoring`),
  getCvTailoringHistory: (workspaceId: string) =>
    request<CVTailoringBatch[]>(`/api/application-workspaces/${workspaceId}/cv-tailoring/history`),

  submitQuestion: (workspaceId: string, questionText: string) =>
    request<ApplicationQuestionResponse>(`/api/application-workspaces/${workspaceId}/questions`, {
      method: "POST",
      body: JSON.stringify({ question_text: questionText }),
    }),
  listQuestions: (workspaceId: string) =>
    request<ApplicationQuestionResponse[]>(`/api/application-workspaces/${workspaceId}/questions`),
  getQuestionHistory: (workspaceId: string, questionText: string) =>
    request<ApplicationQuestionResponse[]>(
      `/api/application-workspaces/${workspaceId}/questions/history${query({
        question_text: questionText,
      })}`
    ),

  generateCoverLetter: (workspaceId: string) =>
    request<CoverLetter>(`/api/application-workspaces/${workspaceId}/cover-letter`, {
      method: "POST",
    }),
  getLatestCoverLetter: (workspaceId: string) =>
    request<CoverLetter | null>(`/api/application-workspaces/${workspaceId}/cover-letter`),
  getCoverLetterHistory: (workspaceId: string) =>
    request<CoverLetter[]>(`/api/application-workspaces/${workspaceId}/cover-letter/history`),

  getCommunicationStyle: () => request<CommunicationStyle>("/api/communication-style"),
  updateCommunicationStyle: (style: CommunicationStyle) =>
    request<CommunicationStyle>("/api/communication-style", {
      method: "PUT",
      body: JSON.stringify(style),
    }),
};
