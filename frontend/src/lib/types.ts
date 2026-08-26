// Mirrors the backend's Pydantic domain models (see backend/app/domain/*.py).
// Kept as one file since the two sides can't share types across the
// Python/TypeScript boundary - this is the single place drift would show up
// when the backend schema changes.

export type RequirementCategory =
  | "technical_skill"
  | "technology"
  | "education"
  | "experience"
  | "domain_knowledge"
  | "soft_skill"
  | "work_rights"
  | "location";

export type RequirementImportance = "required" | "preferred";

export type EvidenceTier = "explicit" | "transferable" | "weak_inference" | "no_evidence";

export type Recommendation = "strong_apply" | "apply" | "stretch" | "low_priority";

export type EmploymentType =
  | "full_time"
  | "part_time"
  | "contract"
  | "internship"
  | "casual"
  | "unknown";

export type SeniorityLevel =
  | "intern"
  | "graduate"
  | "junior"
  | "mid"
  | "senior"
  | "lead"
  | "staff_plus"
  | "unknown";

export type JobPriority = "apply_asap" | "strong_apply" | "apply" | "stretch" | "low_priority";

export type ApplicationStatus =
  | "interested"
  | "applying"
  | "applied"
  | "interview"
  | "rejected"
  | "offer"
  | "withdrawn"
  | "ignored";

export type DiscoveredJobStatus =
  | "discovered"
  | "duplicate"
  | "prefilter_rejected"
  | "awaiting_analysis"
  | "analysing"
  | "analysed"
  | "analysis_failed"
  | "archived";

// --- Candidate ---

export interface Education {
  id?: string | null;
  institution: string;
  qualification: string;
  field_of_study?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  is_current: boolean;
  notes?: string | null;
}

export interface WorkExperience {
  id?: string | null;
  company: string;
  title: string;
  start_date?: string | null;
  end_date?: string | null;
  is_current: boolean;
  summary?: string | null;
  technologies: string[];
}

export interface Evidence {
  id?: string | null;
  source_type: string;
  source_id?: string | null;
  source_label: string;
  statement: string;
  skill_tags: string[];
}

export interface Skill {
  id?: string | null;
  name: string;
  category?: string | null;
  aliases: string[];
  proficiency?: string | null;
}

export interface Project {
  id?: string | null;
  name: string;
  description: string;
  technologies: string[];
  github_url?: string | null;
  highlights: string[];
}

export interface Achievement {
  id?: string | null;
  title: string;
  description?: string | null;
  date?: string | null;
}

export interface Certification {
  id?: string | null;
  name: string;
  issuer?: string | null;
  date?: string | null;
  credential_url?: string | null;
}

export interface CandidatePreferences {
  preferred_job_categories: string[];
  preferred_locations: string[];
  work_rights: string[];
  salary_expectation_min?: number | null;
  salary_expectation_max?: number | null;
  salary_currency: string;
  remote_preference?: string | null;
  preferred_technologies: string[];
  excluded_job_types: string[];
}

export interface Candidate {
  id?: string | null;
  name: string;
  email?: string | null;
  summary?: string | null;
  strengths: string[];
  education: Education[];
  work_history: WorkExperience[];
  skills: Skill[];
  projects: Project[];
  achievements: Achievement[];
  certifications: Certification[];
  evidence: Evidence[];
  preferences: CandidatePreferences;
}

// --- Job + extraction ---

export interface Job {
  id: string;
  title: string;
  company: string;
  location?: string | null;
  source_url?: string | null;
  source_type: string;
  raw_description: string;
  application_status?: ApplicationStatus | null;
  created_at?: string | null;
}

export interface ApplicationStatusEvent {
  id: string;
  job_id: string;
  status: ApplicationStatus;
  note?: string | null;
  created_at?: string | null;
}

export interface SalaryRange {
  min_amount?: number | null;
  max_amount?: number | null;
  currency?: string | null;
  period?: string | null;
}

export interface ExtractedRequirement {
  name: string;
  raw_phrase: string;
  category: RequirementCategory;
  importance: RequirementImportance;
  notes?: string | null;
}

export interface ExtractedJob {
  title: string;
  company: string;
  location?: string | null;
  employment_type: EmploymentType;
  seniority: SeniorityLevel;
  salary?: SalaryRange | null;
  role_category?: string | null;
  requirements: ExtractedRequirement[];
  responsibilities: string[];
  important_phrases: string[];
  extraction_summary?: string | null;
}

// --- Matching ---

export interface RequirementMatch {
  requirement_name: string;
  category: RequirementCategory;
  importance: RequirementImportance;
  tier: EvidenceTier;
  confidence: number;
  evidence_ids: string[];
  evidence_summary?: string | null;
  is_gap: boolean;
}

export interface MatchResult {
  matches: RequirementMatch[];
}

// --- Scoring ---

export interface ScoreComponent {
  name: string;
  raw_score: number;
  weight: number;
  contributing_requirements: number;
  matched_requirements: number;
}

export interface FitScore {
  overall_score: number;
  recommendation: Recommendation;
  technical_fit: ScoreComponent;
  project_relevance_fit: ScoreComponent;
  education_fit: ScoreComponent;
  experience_fit: ScoreComponent;
  domain_fit: ScoreComponent;
  location_fit: ScoreComponent;
  work_rights_fit: ScoreComponent;
  reasoning: string;
}

export interface JobAnalysis {
  id: string;
  job_id: string;
  extracted_job: ExtractedJob;
  match_result: MatchResult;
  fit_score: FitScore;
  created_at?: string | null;
}

// --- Dashboard ---

export interface JobListItem {
  id: string;
  title: string;
  company: string;
  location?: string | null;
  created_at?: string | null;
  latest_overall_score?: number | null;
  latest_recommendation?: string | null;
}

export interface DashboardStats {
  total_jobs: number;
  total_analyses: number;
  strongest_opportunities: JobListItem[];
  recent_analyses: JobListItem[];
  score_distribution: Record<string, number>;
}

export interface CreateJobRequest {
  title: string;
  company: string;
  location?: string | null;
  source_url?: string | null;
  raw_description: string;
}

// --- Discovery ---

export interface SearchProfile {
  id?: string | null;
  name: string;
  keywords: string[];
  locations: string[];
  include_remote: boolean;
  max_experience_level?: SeniorityLevel | null;
  excluded_keywords: string[];
  enabled: boolean;
  source_config: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface DiscoveryRunCounts {
  retrieved: number;
  new: number;
  duplicates: number;
  prefilter_rejected: number;
  eligible: number;
  analysed: number;
  deferred: number;
  failed: number;
  strong_apply_or_better: number;
}

export interface DiscoveryRun {
  id?: string | null;
  status: "running" | "completed" | "failed";
  search_profile_ids: string[];
  sources_used: string[];
  counts: DiscoveryRunCounts;
  estimated_cost_usd: number;
  error_message?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface OpportunityItem {
  discovered_job_id: string;
  job_id?: string | null;
  title: string;
  company: string;
  location?: string | null;
  status: DiscoveredJobStatus;
  prefilter_reason?: string | null;
  search_profile_id?: string | null;
  published_at?: string | null;
  discovered_at?: string | null;
  overall_score?: number | null;
  recommendation?: Recommendation | null;
  priority?: JobPriority | null;
  strong_matches: string[];
  main_gap?: string | null;
  why_summary: string[];
  application_status?: ApplicationStatus | null;
  source_url?: string | null;
}

export interface AppSettings {
  auto_ai_analysis_enabled: boolean;
  max_ai_analyses_per_run: number;
  daily_ai_analysis_budget_usd?: number | null;
}

export interface CostSummary {
  spent_today_usd: number;
  spent_all_time_usd: number;
  daily_budget_usd?: number | null;
}
