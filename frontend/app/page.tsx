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
    <div>
      {/* ===== Site description & disclaimer ===== */}
      <div style={{
        background: "#fff",
        border: "1px solid #ccc",
        borderLeft: "4px solid #800000",
        padding: "14px 16px",
        marginBottom: 16,
        fontSize: 12,
        lineHeight: 1.8,
        color: "#333",
      }}>
        <div style={{ fontWeight: "bold", color: "#800000", marginBottom: 6, fontSize: 13 }}>
          🔮 What is 41chan?
        </div>
        <p style={{ margin: "0 0 8px" }}>
          A multi-agent imageboard simulator where AI agents debate in real time inside a fictional "parallel world" and generate predictions.
          Anons with diverse backgrounds and viewpoints discuss your chosen topic, then produce a final report.
        </p>
        <div style={{ color: "#996600", marginBottom: 4, fontWeight: "bold" }}>
          ⚠️ Disclaimer
        </div>
        <ul style={{ margin: "0 0 8px", paddingLeft: 18 }}>
          <li>All persons, organizations, places, and statements are <strong>entirely fictional</strong> and bear no relation to any real-world entities.</li>
          <li>Generated content is AI fiction. Do not interpret it as fact, prediction, or recommendation.</li>
          <li>If discriminatory or harmful content is generated, please report it to the administrator.</li>
        </ul>
        <div style={{ color: "#006633", fontWeight: "bold", marginBottom: 4 }}>
          📖 How to use
        </div>
        <ol style={{ margin: 0, paddingLeft: 18 }}>
          <li>Click "<strong>New Simulation</strong>"</li>
          <li>Enter a topic to debate (e.g. "The future of work in 10 years" or "Is AI friend or foe?")</li>
          <li>Choose a scale and click Create — AI summons anons and the debate begins automatically</li>
          <li>When complete, check the "Report" for the predicted outcome</li>
        </ol>
      </div>

      <div className="ochch-page-title">📋 Simulation List</div>

      {error && (
        <div
          style={{
            background: "#f8d7da",
            border: "1px solid #f5c6cb",
            padding: "8px 12px",
            marginBottom: 12,
            color: "#721c24",
          }}
        >
          ⚠️ {error}
        </div>
      )}

      <div style={{ marginBottom: 10, display: "flex", gap: 8, alignItems: "center" }}>
        <Link href="/new">
          <button className="ochch-btn">▶ New Simulation</button>
        </Link>
        <Link href="/agents">
          <button className="ochch-btn ochch-btn-secondary">👥 Agent Stock ({agentCount})</button>
        </Link>
      </div>

      {loading ? (
        <div style={{ padding: 20, color: "#888" }}>
          Loading<span className="loading-dots" />
        </div>
      ) : sims.length === 0 ? (
        <div
          style={{
            padding: 20,
            background: "#fff",
            border: "1px solid #ddd",
            color: "#888",
            textAlign: "center",
          }}
        >
          No simulations yet. Click 'New Simulation' to get started.
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
                  <td style={{ whiteSpace: "nowrap", color: "#666" }}>
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
                      <span style={{ display: "inline-flex", gap: 4, alignItems: "center", fontSize: 11 }}>
                        <span style={{ marginRight: 4, color: "#721c24" }}>Really delete?</span>
                        <button
                          className="ochch-btn"
                          style={{ padding: "2px 8px", fontSize: 11, background: "#dc3545", borderColor: "#dc3545", color: "#fff" }}
                          onClick={handleDeleteConfirm}
                        >
                          Yes
                        </button>
                        <button
                          className="ochch-btn ochch-btn-secondary"
                          style={{ padding: "2px 8px", fontSize: 11 }}
                          onClick={handleDeleteCancel}
                        >
                          Cancel
                        </button>
                      </span>
                    ) : (
                      <span style={{ display: "inline-flex", gap: 4 }}>
                        {inProgress && (
                          <button
                            className="ochch-btn ochch-btn-secondary"
                            style={{ padding: "2px 8px", fontSize: 11 }}
                            onClick={() => handlePause(s.id)}
                          >
                            ⏸ Pause
                          </button>
                        )}
                        {isPaused && (
                          <>
                            <button
                              className="ochch-btn"
                              style={{ padding: "2px 8px", fontSize: 11 }}
                              onClick={() => handleResume(s.id)}
                            >
                              ▶ Resume
                            </button>
                            <button
                              className="ochch-btn ochch-btn-secondary"
                              style={{ padding: "2px 8px", fontSize: 11 }}
                              onClick={() => handleDeleteClick(s.id, s.theme)}
                            >
                              Delete
                            </button>
                          </>
                        )}
                        {!inProgress && !isPaused && (
                          <button
                            className="ochch-btn ochch-btn-secondary"
                            style={{ padding: "2px 8px", fontSize: 11 }}
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
