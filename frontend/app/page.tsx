"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, SimulationSummary } from "@/lib/api";

function formatDate(iso: string) {
  try {
    return new Date(iso).toLocaleString("en-US", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function StatusBadge({ status }: { status: string }) {
  const labels: Record<string, string> = {
    initializing: "Initializing",
    planning: "Planning",
    extracting: "Extracting",
    generating_agents: "Generating Agents",
    generating_boards: "Generating Boards",
    simulating: "Simulating",
    reporting: "Generating Report",
    paused: "Paused",
    completed: "Completed",
    failed: "Failed",
  };
  return (
    <span className={`status-badge status-${status}`}>
      {labels[status] || status}
    </span>
  );
}

const IN_PROGRESS_STATUSES = new Set([
  "initializing",
  "planning",
  "extracting",
  "generating_agents",
  "generating_boards",
  "simulating",
  "reporting",
]);

export default function TopPage() {
  const [sims, setSims] = useState<SimulationSummary[]>([]);
  const [agentCount, setAgentCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; theme: string } | null>(null);

  const fetchSims = async () => {
    if (deleteTarget) return;
    try {
      const data = await api.listSimulations();
      setSims(data);
    } catch (e: any) {
      setError("Cannot connect to backend: " + e.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchAgentCount = async () => {
    try {
      const data = await api.getPersistentAgents();
      setAgentCount(data.length);
    } catch {
      // silent
    }
  };

  useEffect(() => {
    fetchSims();
    fetchAgentCount();
    const t = setInterval(fetchSims, 10000);
    return () => clearInterval(t);
  }, [deleteTarget]);

  const handleDeleteClick = (id: string, theme: string) => {
    setDeleteTarget({ id, theme });
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    const { id } = deleteTarget;
    setDeleteTarget(null);
    try {
      await api.deleteSimulation(id);
      setSims((s) => s.filter((x) => x.id !== id));
    } catch (e: any) {
      alert("Delete failed: " + e.message);
    }
  };

  const handleDeleteCancel = () => {
    setDeleteTarget(null);
  };

  const handlePause = async (id: string) => {
    try {
      await api.pauseSimulation(id);
      setSims((s) =>
        s.map((x) => (x.id === id ? { ...x, status: "paused" } : x))
      );
    } catch (e: any) {
      alert("Pause failed: " + e.message);
    }
  };

  const handleResume = async (id: string) => {
    try {
      await api.resumeSimulation(id);
      setSims((s) =>
        s.map((x) => (x.id === id ? { ...x, status: "initializing" } : x))
      );
    } catch (e: any) {
      alert("Resume failed: " + e.message);
    }
  };

  return (
    <div style={{ padding: "0 20px" }}>
      {/* Site description */}
      <div style={{
        background: "#d6daf0",
        border: "1px solid #b7c5d9",
        padding: "12px 14px",
        marginBottom: 16,
        marginTop: 8,
        fontSize: "9pt",
        lineHeight: 1.8,
        color: "#000",
      }}>
        <div style={{ fontWeight: "bold", color: "#af0a0f", marginBottom: 6, fontSize: "10pt" }}>
          What is 41chan?
        </div>
        <p style={{ margin: "0 0 8px" }}>
          A multi-agent imageboard simulator where AI agents debate in real time inside a fictional &quot;parallel world&quot; and generate predictions.
          Anons with diverse backgrounds and viewpoints discuss your chosen topic, then produce a final report.
        </p>
        <div style={{ color: "#af0a0f", marginBottom: 4, fontWeight: "bold" }}>
          Disclaimer
        </div>
        <ul style={{ margin: "0 0 8px", paddingLeft: 18 }}>
          <li>All persons, organizations, places, and statements are <strong>entirely fictional</strong> and bear no relation to any real-world entities.</li>
          <li>Generated content is AI fiction. Do not interpret it as fact, prediction, or recommendation.</li>
          <li>If discriminatory or harmful content is generated, please report it to the administrator.</li>
        </ul>
        <div style={{ color: "#34345c", fontWeight: "bold", marginBottom: 4 }}>
          How to use
        </div>
        <ol style={{ margin: 0, paddingLeft: 18 }}>
          <li>Click &quot;<strong>New Simulation</strong>&quot;</li>
          <li>Enter a topic to debate (e.g. &quot;The future of work in 10 years&quot; or &quot;Is AI friend or foe?&quot;)</li>
          <li>Choose a scale and click Create — AI summons anons and the debate begins automatically</li>
          <li>When complete, check the &quot;Report&quot; for the predicted outcome</li>
        </ol>
      </div>

      <div style={{ fontSize: "10pt", fontWeight: "bold", color: "#af0a0f", marginBottom: 8 }}>
        Simulation List
      </div>

      {error && (
        <div
          style={{
            background: "#d6daf0",
            border: "1px solid #b7c5d9",
            padding: "8px 12px",
            marginBottom: 12,
            color: "#d00000",
            fontSize: "9pt",
          }}
        >
          {error}
        </div>
      )}

      <div style={{ marginBottom: 10, display: "flex", gap: 8, alignItems: "center" }}>
        <Link href="/new">
          <button className="ochch-btn">New Simulation</button>
        </Link>
        <Link href="/agents">
          <button className="ochch-btn">Agent Stock ({agentCount})</button>
        </Link>
      </div>

      {loading ? (
        <div style={{ padding: 20, color: "#707070" }}>
          Loading<span className="loading-dots" />
        </div>
      ) : sims.length === 0 ? (
        <div
          style={{
            padding: 20,
            background: "#d6daf0",
            border: "1px solid #b7c5d9",
            color: "#707070",
            textAlign: "center",
            fontSize: "9pt",
          }}
        >
          No simulations yet. Click &apos;New Simulation&apos; to get started.
        </div>
      ) : (
        <table className="sim-list">
          <thead>
            <tr>
              <th>Theme</th>
              <th>Status</th>
              <th>Boards</th>
              <th>Total Posts</th>
              <th>Duration</th>
              <th>Created</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {sims.map((s) => {
              const isDeleteTargetRow = deleteTarget?.id === s.id;
              const inProgress = IN_PROGRESS_STATUSES.has(s.status);
              const isPaused = s.status === "paused";

              return (
                <tr key={s.id}>
                  <td>
                    <Link href={`/sim/${s.id}`}>
                      {s.theme || s.id.slice(0, 8)}
                    </Link>
                  </td>
                  <td>
                    <StatusBadge status={s.status} />
                  </td>
                  <td>{s.board_count}</td>
                  <td>{s.total_posts}</td>
                  <td style={{ whiteSpace: "nowrap", color: "#707070" }}>
                    {s.elapsed_seconds != null && s.elapsed_seconds > 0
                      ? s.elapsed_seconds >= 60
                        ? `${Math.floor(s.elapsed_seconds / 60)}m${Math.round(s.elapsed_seconds % 60)}s`
                        : `${Math.round(s.elapsed_seconds)}s`
                      : "—"}
                  </td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    {formatDate(s.created_at)}
                  </td>
                  <td>
                    {isDeleteTargetRow ? (
                      <span style={{ display: "inline-flex", gap: 4, alignItems: "center", fontSize: "9pt" }}>
                        <span style={{ marginRight: 4, color: "#d00000" }}>Really delete?</span>
                        <button
                          className="ochch-btn"
                          style={{ padding: "2px 8px", fontSize: "9pt", color: "#d00000" }}
                          onClick={handleDeleteConfirm}
                        >
                          Yes
                        </button>
                        <button
                          className="ochch-btn"
                          style={{ padding: "2px 8px", fontSize: "9pt" }}
                          onClick={handleDeleteCancel}
                        >
                          Cancel
                        </button>
                      </span>
                    ) : (
                      <span style={{ display: "inline-flex", gap: 4 }}>
                        {inProgress && (
                          <button
                            className="ochch-btn"
                            style={{ padding: "2px 8px", fontSize: "9pt" }}
                            onClick={() => handlePause(s.id)}
                          >
                            Pause
                          </button>
                        )}
                        {isPaused && (
                          <>
                            <button
                              className="ochch-btn"
                              style={{ padding: "2px 8px", fontSize: "9pt" }}
                              onClick={() => handleResume(s.id)}
                            >
                              Resume
                            </button>
                            <button
                              className="ochch-btn"
                              style={{ padding: "2px 8px", fontSize: "9pt" }}
                              onClick={() => handleDeleteClick(s.id, s.theme)}
                            >
                              Delete
                            </button>
                          </>
                        )}
                        {!inProgress && !isPaused && (
                          <button
                            className="ochch-btn"
                            style={{ padding: "2px 8px", fontSize: "9pt" }}
                            onClick={() => handleDeleteClick(s.id, s.theme)}
                          >
                            Delete
                          </button>
                        )}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
