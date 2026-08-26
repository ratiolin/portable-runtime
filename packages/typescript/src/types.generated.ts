// Structural DTOs generated from contracts/. Do not add semantic authority here.

export type ExperienceUseStatus =
  | "not-applicable"
  | "allowed"
  | "blocked"
  | "stale"
  | "unavailable";

export interface ExperienceUseRequirementV1 {
  schema: "experience-use-requirement-v1";
  projection_refs: string[];
  use_scope: Record<string, unknown>;
  subject_version_refs: string[];
  environment_bindings: Record<string, string>;
  use_context: Record<string, unknown>;
}

export interface ExperienceUseAdmissionV1 {
  admission_contract_version: "experience-use-admission-v1";
  status: ExperienceUseStatus;
  requirement_digest: string;
  snapshot_digest: string;
  resolved_snapshot: Record<string, unknown>;
  reasons: string[];
}

export interface HistoricalExperienceUseV1 {
  id: string;
  judgment_ref: string;
  judgment_version: number;
  requirement_digest: string;
  snapshot_digest: string;
  snapshot_semantic_json: string;
  selected_projection_refs: string[];
  admission_contract_version: string;
}

export interface HistoricalExperienceUseCommitV1 {
  schema: "historical-experience-use-commit-v1";
  judgment: Record<string, unknown>;
  requirement: ExperienceUseRequirementV1;
  expected_requirement_digest: string;
  expected_snapshot_digest: string;
  expected_admission_contract_version?: string | null;
}

export interface ApiProblemV1 {
  schema: "api-problem-v1";
  code: string;
  message: string;
  details?: Record<string, unknown>;
  retryable?: boolean;
}

export interface GovernanceUseAdmissionView {
  schema: "governance-use-admission-view-v1";
  status: string;
  scheme_id?: string | null;
  requirement_digest?: string | null;
  snapshot_digest?: string | null;
  reasons: string[];
  authority_bearing: false;
}

export interface InvocationPermitView {
  schema: "invocation-permit-view-v1";
  permit_digest: string;
  provider_id?: string | null;
  qualification_digest?: string | null;
  governance_bound: boolean;
  governance_requirement_digest?: string | null;
  governance_snapshot_digest?: string | null;
  issued_at?: string | null;
  authority_bearing: false;
}

export interface InvocationDispatchCommittedView {
  schema: "invocation-dispatch-committed-view-v1";
  event_id: string;
  request_id?: string | null;
  provider_id?: string | null;
  attempt_id?: string | null;
  permit_digest?: string | null;
  qualification_digest?: string | null;
  governance_requirement_digest?: string | null;
  governance_snapshot_digest?: string | null;
  authority_bearing: false;
}

export interface ConfirmedOutcomeView {
  schema: "confirmed-outcome-view-v1";
  outcome_id: string;
  action_ref?: string | null;
  status: string;
  verification_refs: string[];
  authority_bearing: false;
}

export interface RecoveryView {
  schema: "recovery-view-v1";
  subject_ref: string;
  observation?: Record<string, unknown> | null;
  disposition?: Record<string, unknown> | null;
  application?: Record<string, unknown> | null;
  authority_bearing: false;
}
