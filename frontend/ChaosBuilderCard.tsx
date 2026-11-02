import React, { useState } from "react";
import {
  FaultCategory,
  TriggerStrategy,
  useChaosStream,
} from "./useChaosStream";


interface ChaosBuilderCardProps {
  apiBasePath: string;
  githubHandle: string;
  sandboxName?: string;
}


export const ChaosBuilderCard: React.FC<ChaosBuilderCardProps> = ({
  apiBasePath,
  githubHandle,
  sandboxName = "mcp-chaos-prod (2 vCPU / 4 GiB Cloud microVM)",
}) => {
  const [githubVerified, setGithubVerified] = useState<boolean>(true);
  const {
    events,
    isStreaming,
    selectedStrategy,
    selectedFault,
    totalCalls,
    totalFaultsFired,
    passAtOneRate,
    hasOmissionSignature,
    setSelectedStrategy,
    setSelectedFault,
    startChaosStream,
  } = useChaosStream(apiBasePath, `sess-${githubHandle}`);


  return (
    <main
      style={{
        maxWidth: "960px",
        margin: "0 auto",
        padding: "24px",
        fontFamily: "system-ui, -apple-system, sans-serif",
        backgroundColor: "#0b0f19",
        color: "#f8fafc",
        borderRadius: "16px",
      }}
    >
      {/* Header & GitHub Opt-In Builder Card Badge */}
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          borderBottom: "1px solid #1e293b",
          paddingBottom: "16px",
          marginBottom: "20px",
        }}
      >
        <div>
          <h1 style={{ margin: 0, fontSize: "1.5rem" }}>
            MCP Chaos Sandbox — Builder Resilience Card
          </h1>
          <p style={{ margin: "4px 0 0", color: "#94a3b8", fontSize: "0.9rem" }}>
            Runtime: {sandboxName} | Secrets: Out-of-Band Host Proxy
          </p>
        </div>
        <button
          type="button"
          onClick={() => setGithubVerified((prev) => !prev)}
          style={{
            padding: "8px 14px",
            borderRadius: "8px",
            border: "1px solid #334155",
            backgroundColor: githubVerified ? "#065f46" : "#1e293b",
            color: "#fff",
            cursor: "pointer",
            fontWeight: 600,
          }}
        >
          {githubVerified
            ? `GitHub Verified: @${githubHandle}`
            : "Connect GitHub OAuth"}
        </button>
      </header>


      {/* Top KPI Strip */}
      <section
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: "12px",
          marginBottom: "20px",
        }}
      >
        <div style={{ background: "#111827", padding: "14px", borderRadius: "10px" }}>
          <div style={{ color: "#94a3b8", fontSize: "0.8rem" }}>Pass@1 Resilience</div>
          <div style={{ fontSize: "1.6rem", fontWeight: 700, color: "#34d399" }}>
            {passAtOneRate}%
          </div>
        </div>
        <div style={{ background: "#111827", padding: "14px", borderRadius: "10px" }}>
          <div style={{ color: "#94a3b8", fontSize: "0.8rem" }}>MCP Transport Calls</div>
          <div style={{ fontSize: "1.6rem", fontWeight: 700 }}>{totalCalls}</div>
        </div>
        <div style={{ background: "#111827", padding: "14px", borderRadius: "10px" }}>
          <div style={{ color: "#94a3b8", fontSize: "0.8rem" }}>Faults Injected</div>
          <div style={{ fontSize: "1.6rem", fontWeight: 700, color: "#fbbf24" }}>
            {totalFaultsFired}
          </div>
        </div>
        <div style={{ background: "#111827", padding: "14px", borderRadius: "10px" }}>
          <div style={{ color: "#94a3b8", fontSize: "0.8rem" }}>MCP-38 Guardrail</div>
          <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "#60a5fa" }}>
            Active (70% Floor)
          </div>
        </div>
      </section>


      {/* Fault Injection Controls */}
      <section
        style={{
          display: "flex",
          gap: "12px",
          alignItems: "center",
          background: "#1e293b",
          padding: "16px",
          borderRadius: "12px",
          marginBottom: "20px",
        }}
      >
        <label>
          Fault Category:{" "}
          <select
            value={selectedFault}
            onChange={(e) => setSelectedFault(e.target.value as FaultCategory)}
            style={{ padding: "6px", borderRadius: "6px" }}
          >
            <option value="omission">Omission (30% Truncation + length)</option>
            <option value="crash">Crash (HTTP 500 / Timeout)</option>
            <option value="value">Value (Malformed JSON / Drift)</option>
            <option value="none">Clean Baseline</option>
          </select>
        </label>


        <label>
          Trigger Strategy:{" "}
          <select
            value={selectedStrategy}
            onChange={(e) => setSelectedStrategy(e.target.value as TriggerStrategy)}
            style={{ padding: "6px", borderRadius: "6px" }}
          >
            <option value="burst">Burst (3 Consecutive Calls)</option>
            <option value="intermittent">Intermittent (0.30 Prob)</option>
            <option value="single">Single (1st Matching Call)</option>
            <option value="persistent">Persistent (Trip Loop Breaker)</option>
          </select>
        </label>


        <button
          type="button"
          onClick={startChaosStream}
          disabled={isStreaming}
          style={{
            marginLeft: "auto",
            padding: "10px 18px",
            borderRadius: "8px",
            border: "none",
            backgroundColor: "#3b82f6",
            color: "#fff",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          {isStreaming ? "Streaming Chaos Suite..." : "Run Cloud Chaos Suite"}
        </button>
      </section>


      {/* Diagnostic Alert for Omission vs Model Weakness */}
      {hasOmissionSignature && (
        <div
          style={{
            backgroundColor: "#451a03",
            border: "1px solid #f59e0b",
            padding: "12px 16px",
            borderRadius: "10px",
            marginBottom: "16px",
            color: "#fde68a",
          }}
        >
          <strong>Diagnostic Telemetry Alert:</strong> Detected HTTP 200 with{" "}
          <code>finish_reason: length</code> at 100% token ratio. Classified as{" "}
          <strong>Transport Omission Fault (30% payload truncation)</strong> — not
          model reasoning failure. Self-correction triggered.
        </div>
      )}


      {/* Live SSE Telemetry Table */}
      <section
        style={{
          background: "#111827",
          borderRadius: "12px",
          padding: "16px",
        }}
      >
        <h2 style={{ marginTop: 0, fontSize: "1.1rem" }}>
          Live ContextVars-Isolated Telemetry Stream
        </h2>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.9rem" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid #334155", textAlign: "left" }}>
              <th style={{ padding: "8px" }}>Call #</th>
              <th style={{ padding: "8px" }}>Fault / Strategy</th>
              <th style={{ padding: "8px" }}>HTTP</th>
              <th style={{ padding: "8px" }}>finish_reason</th>
              <th style={{ padding: "8px" }}>Token Ratio</th>
              <th style={{ padding: "8px" }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {events.map((ev) => (
              <tr key={ev.call_counter} style={{ borderBottom: "1px solid #1e293b" }}>
                <td style={{ padding: "8px" }}>#{ev.call_counter}</td>
                <td style={{ padding: "8px" }}>
                  {ev.fault_category} ({ev.strategy})
                </td>
                <td style={{ padding: "8px" }}>{ev.http_status}</td>
                <td style={{ padding: "8px" }}>
                  <code>{ev.finish_reason}</code>
                </td>
                <td style={{ padding: "8px" }}>
                  {Math.round(ev.token_utilization_ratio * 100)}%
                </td>
                <td style={{ padding: "8px", color: ev.recovered ? "#34d399" : "#f87171" }}>
                  {ev.recovered ? "Recovered" : "Loop Halted"} — {ev.detail}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
};