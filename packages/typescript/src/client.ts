import type {
  ApiProblemV1,
  ExperienceUseAdmissionV1,
  ExperienceUseRequirementV1,
  HistoricalExperienceUseCommitV1,
  HistoricalExperienceUseV1,
} from "./types.generated.js";

const SUPPORTED_CATALOG_VERSION = "portable-runtime-contracts-v1";
const SUPPORTED_OWNER = "portable-runtime/contracts";

export class PortableRuntimeContractError extends Error {
  constructor(readonly problem: ApiProblemV1, readonly status: number) {
    super(problem.message);
    this.name = "PortableRuntimeContractError";
  }
}

export class ContractVersionMismatch extends Error {
  constructor(readonly received: unknown) {
    super(`unsupported portable-runtime contract catalog: ${String(received)}`);
    this.name = "ContractVersionMismatch";
  }
}

export class PortableRuntimeClient {
  constructor(
    readonly baseUrl = "http://127.0.0.1:8000",
    readonly fetcher: typeof fetch = fetch,
  ) {}

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await this.fetcher(`${this.baseUrl}${path}`, {
      ...init,
      headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
    });
    const payload = await response.json();
    if (!response.ok) {
      const detail = (payload?.detail ?? payload) as ApiProblemV1;
      throw new PortableRuntimeContractError(detail, response.status);
    }
    return payload as T;
  }

  async contracts(): Promise<Record<string, unknown>> {
    const payload = await this.request<Record<string, unknown>>("/v1/contracts");
    if (
      payload.catalog_version !== SUPPORTED_CATALOG_VERSION ||
      payload.owner !== SUPPORTED_OWNER
    ) {
      throw new ContractVersionMismatch(payload.catalog_version);
    }
    return payload;
  }

  evaluateExperience(requirement: ExperienceUseRequirementV1): Promise<ExperienceUseAdmissionV1> {
    return this.request("/v1/experience/use/evaluate", {
      method: "POST",
      body: JSON.stringify(requirement),
    });
  }

  commitHistoricalExperienceUse(
    command: HistoricalExperienceUseCommitV1,
  ): Promise<HistoricalExperienceUseV1> {
    return this.request("/v1/experience/historical-use/commit", {
      method: "POST",
      body: JSON.stringify(command),
    });
  }

  historicalExperienceUse(judgmentId: string): Promise<HistoricalExperienceUseV1> {
    return this.request(`/v1/experience/historical-use/${encodeURIComponent(judgmentId)}`);
  }
}

// Deliberately absent: policy evaluation, qualification, authority inference,
// InvocationPermit construction, GovernanceUseRequirement construction,
// authoritative digest generation, dispatch commitment and reconciliation authority.
