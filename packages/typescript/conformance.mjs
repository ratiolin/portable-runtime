import fs from "node:fs";

const vectorsUrl = new URL("../../contracts/vectors/experience/v1.json", import.meta.url);
const workflowUrl = new URL("./src/workflow.ts", import.meta.url);
const clientUrl = new URL("./src/client.ts", import.meta.url);
const typesUrl = new URL("./src/types.generated.ts", import.meta.url);

const document = JSON.parse(fs.readFileSync(vectorsUrl, "utf8"));
if (document.schema !== "portable-runtime-conformance-vectors-v1") {
  throw new Error("unsupported conformance vector schema");
}

const vectors = new Map(document.vectors.map((vector) => [vector.id, vector]));
const required = [
  "EU-001", "EU-002", "EU-003", "EU-004", "EU-005", "EU-006", "EU-007", "EU-008",
  "HU-001", "HU-002", "HU-003", "HU-004", "HU-005", "HU-006",
];
for (const id of required) {
  if (!vectors.has(id)) throw new Error(`missing public contract vector ${id}`);
}

const expectedStatuses = new Map([
  ["EU-003", "not-applicable"],
  ["EU-004", "unavailable"],
  ["EU-005", "blocked"],
  ["EU-006", "stale"],
]);
for (const [id, status] of expectedStatuses) {
  if (vectors.get(id)?.expect?.status !== status) {
    throw new Error(`${id} status mapping drifted`);
  }
}

const unicode = vectors.get("EU-002");
if (unicode?.given?.use_context?.["语言"] !== "中文" || unicode?.given?.use_context?.["地点"] !== "東京") {
  throw new Error("EU-002 Unicode fixture drifted");
}
if (unicode?.expect?.sha256 !== "3c1ed9883f948d54347e975daeb87cb148c3cac2aa74800a37c50538c10a0196") {
  throw new Error("EU-002 authoritative Python digest expectation drifted");
}

const workflow = fs.readFileSync(workflowUrl, "utf8");
for (const marker of ["evaluateExperience", "bindHistoricalUse", "Execution remains a separate"]) {
  if (!workflow.includes(marker)) throw new Error(`workflow responsibility cut missing: ${marker}`);
}
if (workflow.includes("useKnowledgeAndDecideAndExecute(")) {
  throw new Error("combined decision/execution shortcut is forbidden");
}

const client = fs.readFileSync(clientUrl, "utf8");
const types = fs.readFileSync(typesUrl, "utf8");
for (const authorityName of ["GovernanceUseRequirement", "InvocationPermit"]) {
  if (types.includes(`interface ${authorityName} `) || types.includes(`type ${authorityName} =`)) {
    throw new Error(`TypeScript must not define authority object ${authorityName}`);
  }
}
for (const marker of ["ContractVersionMismatch", "portable-runtime-contracts-v1", "portable-runtime/contracts"]) {
  if (!client.includes(marker)) throw new Error(`contract negotiation fail-closed marker missing: ${marker}`);
}

console.log(JSON.stringify({ verified: required, authority: "non-authoritative-consumer" }));
