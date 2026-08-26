import { useState } from "react";

type Historical = {
  id: string;
  judgment_ref: string;
  judgment_version: number;
  requirement_digest: string;
  snapshot_digest: string;
  snapshot_semantic_json: string;
  selected_projection_refs: string[];
  admission_contract_version: string;
};

const sections = [
  ["CURRENT", "Why is current use allowed or blocked?"],
  ["HISTORICAL", "What exact experience was actually relied on?"],
  ["DIFF", "What changed between the historical snapshot and current state?"],
  ["AUTHORITY", "Which authority allowed each responsibility transition?"],
  ["OPEN RESPONSIBILITY", "Which obligation remains undischarge?"],
  ["SHORTCUT", "Why is a downstream action currently not admissible?"],
] as const;

export function App() {
  const [baseUrl, setBaseUrl] = useState("http://127.0.0.1:8000");
  const [judgmentId, setJudgmentId] = useState("");
  const [historical, setHistorical] = useState<Historical | null>(null);
  const [error, setError] = useState("");

  async function inspect() {
    setError("");
    setHistorical(null);
    const response = await fetch(
      `${baseUrl}/v1/experience/historical-use/${encodeURIComponent(judgmentId)}`,
    );
    if (!response.ok) {
      setError(`HTTP ${response.status}`);
      return;
    }
    setHistorical((await response.json()) as Historical);
  }

  const snapshot = historical
    ? JSON.parse(historical.snapshot_semantic_json) as Record<string, unknown>
    : null;

  return (
    <main>
      <header>
        <p className="eyebrow">PORTABLE RUNTIME</p>
        <h1>Responsibility Inspector</h1>
        <p>Read-only inspection of current, historical, authority and open-responsibility facts.</p>
      </header>

      <section className="query">
        <label>
          Runtime URL
          <input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} />
        </label>
        <label>
          Judgment ID
          <input value={judgmentId} onChange={(event) => setJudgmentId(event.target.value)} />
        </label>
        <button onClick={inspect} disabled={!judgmentId}>Inspect</button>
      </section>

      {error && <p className="error">{error}</p>}

      <div className="grid">
        {sections.map(([name, question]) => (
          <section className="card" key={name}>
            <h2>{name}</h2>
            <p>{question}</p>
            {name === "HISTORICAL" && historical && (
              <dl>
                <dt>Binding</dt><dd>{historical.id}</dd>
                <dt>Judgment</dt><dd>{historical.judgment_ref}:v{historical.judgment_version}</dd>
                <dt>Requirement digest</dt><dd>{historical.requirement_digest}</dd>
                <dt>Snapshot digest</dt><dd>{historical.snapshot_digest}</dd>
                <dt>Projections</dt><dd>{historical.selected_projection_refs.join(", ") || "none"}</dd>
              </dl>
            )}
            {name === "CURRENT" && snapshot && (
              <pre>{JSON.stringify(snapshot, null, 2)}</pre>
            )}
            {(name === "AUTHORITY" || name === "OPEN RESPONSIBILITY" || name === "SHORTCUT" || name === "DIFF") && (
              <p className="muted">This read-only shell intentionally does not infer missing authority or obligations. It displays only durable/public facts as corresponding contract views are available.</p>
            )}
          </section>
        ))}
      </div>

      <footer>
        The Inspector cannot mint decisions, authorizations, permits, governance requirements or execution commands.
      </footer>
    </main>
  );
}
