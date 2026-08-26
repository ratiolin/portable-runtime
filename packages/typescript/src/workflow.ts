import { PortableRuntimeClient } from "./client.js";
import type {
  ExperienceUseAdmissionV1,
  ExperienceUseRequirementV1,
  HistoricalExperienceUseV1,
} from "./types.generated.js";

export interface DomainJudgmentInput {
  id: string;
  version: number;
  statement: string;
  [key: string]: unknown;
}

/**
 * A deliberately explicit workflow helper.
 *
 * It preserves the responsibility cuts instead of providing a
 * useKnowledgeAndDecideAndExecute shortcut.
 */
export class ResponsibilityWorkflow {
  constructor(readonly client: PortableRuntimeClient) {}

  evaluateExperience(requirement: ExperienceUseRequirementV1): Promise<ExperienceUseAdmissionV1> {
    return this.client.evaluateExperience(requirement);
  }

  async bindHistoricalUse(params: {
    judgment: DomainJudgmentInput;
    requirement: ExperienceUseRequirementV1;
    evaluated: ExperienceUseAdmissionV1;
  }): Promise<HistoricalExperienceUseV1> {
    if (params.evaluated.status !== "allowed") {
      throw new Error(`historical use requires allowed current admission, got ${params.evaluated.status}`);
    }
    return this.client.commitHistoricalExperienceUse({
      schema: "historical-experience-use-commit-v1",
      judgment: params.judgment,
      requirement: params.requirement,
      expected_requirement_digest: params.evaluated.requirement_digest,
      expected_snapshot_digest: params.evaluated.snapshot_digest,
      expected_admission_contract_version: params.evaluated.admission_contract_version,
    });
  }
}

// Execution remains a separate runtime capability/authorization path and is
// intentionally not composed into this workflow helper.
