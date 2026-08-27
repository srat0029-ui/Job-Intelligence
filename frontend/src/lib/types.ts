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

export type ATSType = "lever" | "greenhouse";

export type CompanyPriority = "high" | "normal" | "low";

export type SourceHealthStatus = "healthy" | "degraded" | "error" | "unknown";

export type DuplicateMatchStage =
  | "exact_id"
  | "canonical_url"
  | "deterministic_fingerprint"
  | "fuzzy"
  | "original";

export type AttentionItemType =
  | "high_priority_job"
  | "watchlist_company_posting"
  | "analysis_failures"
  | "source_unhealthy";

export type AttentionItemStatus = "unread" | "read";

// --- Milestone 4A: Application Intelligence ---

export type ResearchSourceType =
  | "official_website"
  | "careers_page"
  | "engineering_blog"
  | "press_release"
  | "news"
  | "company_directory"
  | "other";

export type SourceQualityTier = "high" | "medium" | "low";

export type ClaimVerificationStatus = "verified_fact" | "reasonable_inference" | "unknown";

export type ResearchFetchStatus = "success" | "failed";

export type GapStrategyCategory =
  | "acknowledge_honestly"
  | "demonstrate_transferable"
  | "provide_project_evidence"
  | "show_rapid_learning"
  | "do_not_address";

export type EvidenceStrength = "strong" | "partial" | "weak" | "gap";

export type GenerationStatus = "draft" | "reviewed" | "needs_review" | "archived";

export type ReviewVerdict = "pass" | "pass_with_warnings" | "fail";

export type QuestionType =
  | "motivation"
  | "company_motivation"
  | "technical_experience"
  | "behavioural"
  | "values"
  | "teamwork"
  | "leadership"
  | "problem_solving"
  | "learning"
  | "project_experience"
  | "work_rights"
  | "salary"
  | "general_background";

export type CVSection = "summary" | "education" | "employment" | "project" | "skill" | "certification";

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
  career_stage_fit?: ScoreComponent | null;
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
  application_status?: ApplicationStatus | null;
  source_url?: string | null;
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

export interface KeywordGroup {
  name: string;
  keywords: string[];
}

export interface SearchProfile {
  id?: string | null;
  name: string;
  keywords: string[];
  keyword_groups: KeywordGroup[];
  locations: string[];
  location_priority: Record<string, number>;
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
  ai_calls: number;
  ai_input_tokens: number;
  ai_output_tokens: number;
}

export interface DiscoveryRun {
  id?: string | null;
  status: "running" | "completed" | "failed";
  search_profile_ids: string[];
  sources_used: string[];
  counts: DiscoveryRunCounts;
  estimated_cost_usd: number;
  error_message?: string | null;
  triggered_by: string;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface DiscoveredJob {
  id?: string | null;
  source: string;
  external_id?: string | null;
  source_url?: string | null;
  title: string;
  company: string;
  raw_description: string;
  location?: string | null;
  remote_type?: string | null;
  salary_min?: number | null;
  salary_max?: number | null;
  currency?: string | null;
  employment_type?: string | null;
  published_at?: string | null;
  retrieved_at?: string | null;
  status: DiscoveredJobStatus;
  prefilter_reason?: string | null;
  search_profile_id?: string | null;
  discovery_run_id?: string | null;
  job_id?: string | null;
  analysis_priority?: number | null;
  latest_overall_score?: number | null;
  latest_recommendation?: string | null;
  latest_priority?: string | null;
  reviewed_at?: string | null;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  times_seen: number;
  created_at?: string | null;
  updated_at?: string | null;
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
  reviewed_at?: string | null;
  salary_min?: number | null;
  salary_max?: number | null;
  currency?: string | null;
  source?: string | null;
}

export interface OpportunityPage {
  items: OpportunityItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface AppSettings {
  auto_ai_analysis_enabled: boolean;
  max_ai_analyses_per_run: number;
  daily_ai_analysis_budget_usd?: number | null;
  auto_discovery_enabled: boolean;
  discovery_frequency_hours: number;
  max_postings_per_source_per_run: number;
  last_scheduled_run_at?: string | null;
  next_scheduled_run_at?: string | null;
  gmail_sync_frequency_minutes: number;
  next_gmail_sync_at?: string | null;
}

export interface CostSummary {
  spent_today_usd: number;
  spent_all_time_usd: number;
  daily_budget_usd?: number | null;
}

export interface GmailStatus {
  connected: boolean;
  connected_email?: string | null;
  connected_at?: string | null;
  last_sync_at?: string | null;
  last_sync_status?: string | null;
  last_sync_message?: string | null;
}

// --- Company watchlist ---

export interface CompanyWatchlistEntry {
  id?: string | null;
  company_name: string;
  enabled: boolean;
  priority: CompanyPriority;
  careers_url?: string | null;
  ats_type: ATSType;
  ats_identifier: string;
  preferred_locations: string[];
  notes?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

// --- Source health ---

export interface SourceHealth {
  source_key: string;
  status: SourceHealthStatus;
  last_attempt_at?: string | null;
  last_success_at?: string | null;
  consecutive_failures: number;
  last_error_category?: string | null;
  jobs_retrieved_last_run: number;
  avg_latency_ms?: number | null;
  attempts_count: number;
}

// --- Attention / notifications ---

export interface AttentionItem {
  id?: string | null;
  item_type: AttentionItemType;
  title: string;
  message: string;
  related_discovered_job_id?: string | null;
  related_job_id?: string | null;
  related_company?: string | null;
  status: AttentionItemStatus;
  created_at?: string | null;
}

// --- Dashboard ---

export interface DiscoveryDashboardStats {
  new_jobs_today: number;
  high_priority_unreviewed: number;
  unread_attention_count: number;
  auto_discovery_enabled: boolean;
  last_scheduled_run_at?: string | null;
  next_scheduled_run_at?: string | null;
  source_health: SourceHealth[];
}

// --- Milestone 4A: Application Intelligence ---

export interface ApplicationWorkspace {
  id: string;
  job_id: string;
  notes?: string | null;
  research_company_name?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface GenerationMeta {
  version: number;
  status: GenerationStatus;
  prompt_version: string;
  model: string;
  generated_at?: string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  estimated_cost_usd?: number | null;
  reviewer_result?: ReviewVerdict | null;
  reviewer_issues: string[];
  regeneration_attempt: number;
}

export interface ResearchSource {
  id?: string | null;
  company_name: string;
  url: string;
  domain: string;
  title?: string | null;
  source_type: ResearchSourceType;
  source_quality: SourceQualityTier;
  fetch_status: ResearchFetchStatus;
  raw_text_excerpt?: string | null;
  published_at?: string | null;
  retrieved_at?: string | null;
  error_message?: string | null;
  created_at?: string | null;
}

export interface ResearchClaim {
  id?: string | null;
  research_source_id: string;
  company_name: string;
  category: string;
  claim: string;
  supporting_excerpt: string;
  verification_status: ClaimVerificationStatus;
  confidence: number;
  is_stale: boolean;
  created_at?: string | null;
}

export interface CompanyResearchBundle {
  company_name: string;
  sources: ResearchSource[];
  claims: ResearchClaim[];
}

export interface RequirementCoverage {
  requirement_name: string;
  importance: RequirementImportance;
  strength: EvidenceStrength;
}

export interface GapStrategyItem {
  requirement_name: string;
  strategy_category: GapStrategyCategory;
  guidance: string;
  adjacent_evidence_ids: string[];
}

export interface GapAnalysis {
  id?: string | null;
  workspace_id: string;
  job_analysis_id: string;
  coverage: RequirementCoverage[];
  gap_strategies: GapStrategyItem[];
}

export interface ConcernItem {
  concern: string;
  response_strategy: string;
}

export interface ApplicationStrategy {
  id?: string | null;
  workspace_id: string;
  gap_analysis_id: string;
  positioning: string;
  lead_evidence_ids: string[];
  skills_to_emphasise: string[];
  skills_to_deemphasise: string[];
  likely_concerns: ConcernItem[];
  motivation_themes: string[];
  application_priority?: string | null;
  recommendation: string;
  source_evidence_ids: string[];
  source_research_claim_ids: string[];
  meta: GenerationMeta;
  created_at?: string | null;
}

export interface CVBulletSuggestion {
  section: CVSection;
  source_ref_label: string;
  original_text: string;
  suggested_text: string;
  relevance_rank: number;
  supporting_evidence_ids: string[];
  passed_grounding_check: boolean;
  grounding_issues: string[];
}

export interface CVTailoringBatch {
  id?: string | null;
  workspace_id: string;
  suggestions: CVBulletSuggestion[];
  section_emphasis: string[];
  source_evidence_ids: string[];
  meta: GenerationMeta;
  created_at?: string | null;
}

export interface ApplicationQuestionResponse {
  id?: string | null;
  workspace_id: string;
  question_text: string;
  classifications: QuestionType[];
  answered_deterministically: boolean;
  response_text: string;
  source_evidence_ids: string[];
  source_research_claim_ids: string[];
  meta: GenerationMeta;
  created_at?: string | null;
}

export interface CoverLetter {
  id?: string | null;
  workspace_id: string;
  body: string;
  source_evidence_ids: string[];
  source_research_claim_ids: string[];
  meta: GenerationMeta;
  created_at?: string | null;
}

export interface CommunicationStyle {
  tone: string;
  avoid_buzzwords: boolean;
  avoid_exaggerated_claims: boolean;
  prefer_specific_examples: boolean;
  avoid_em_dashes: boolean;
  region_convention: string;
}

export interface BriefEvidenceItem {
  evidence_id: string;
  label: string;
}

export interface ApplicationBrief {
  why_this_role_fits: string[];
  best_evidence_to_use: BriefEvidenceItem[];
  key_gaps: string[];
  how_to_position: string[];
  company_talking_points: string[];
  likely_application_themes: string[];
}

export interface WorkspaceOverview {
  workspace: ApplicationWorkspace;
  job: Job;
  overall_score?: number | null;
  recommendation?: string | null;
  application_status?: string | null;
  strongest_evidence_labels: string[];
  main_gaps: string[];
  research_source_count: number;
  research_claim_count: number;
  has_strategy: boolean;
  has_cv_tailoring: boolean;
  has_cover_letter: boolean;
  question_count: number;
  brief?: ApplicationBrief | null;
}

export interface WorkspaceTraceCall {
  operation_type: string;
  input_identifier: string;
  prompt_version: string;
  model: string;
  status: string;
  input_tokens?: number | null;
  output_tokens?: number | null;
  estimated_cost_usd?: number | null;
  created_at?: string | null;
}

export interface WorkspaceTrace {
  workspace_id: string;
  ai_calls: WorkspaceTraceCall[];
  total_estimated_cost_usd: number;
}

// --- Application Pack (simplified one-click "Prepare Application") ---

export interface ApplicationPack {
  workspace_id: string;
  job_id: string;
  job_title: string;
  company: string;
  original_url?: string | null;
  application_status?: ApplicationStatus | null;
  brief: ApplicationBrief;
  cv_suggestions: CVBulletSuggestion[];
  cv_reviewer_result?: ReviewVerdict | null;
  cover_letter_body?: string | null;
  cover_letter_reviewer_result?: ReviewVerdict | null;
  cover_letter_reviewer_issues: string[];
  generated_at?: string | null;
}
