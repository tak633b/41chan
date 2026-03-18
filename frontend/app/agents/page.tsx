"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, PersistentAgent } from "@/lib/api";

const POSTING_STYLE_LABELS: Record<string, string> = {
  info_provider: "📚 Info Provider",
  debater: "⚔️ Debater",
  joker: "🃏 Joker",
  questioner: "❓ Questioner",
  veteran: "👴 Veteran",
  passerby: "🚶 Passerby",
  emotional: "😂 Emotional",
  storyteller: "📖 Storyteller",
  agreeer: "👍 Agreeist",
  contrarian: "🔄 Contrarian",
};

const GENDER_LABEL: Record<string, string> = {
  male: "♂ Male",
  female: "♀ Female",
  other: "⚧ Other",
};

function AgentDetailModal({
  agent,
  onClose,
  onRate,
  onToggleActive,
}: {
  agent: PersistentAgent;
  onClose: () => void;
  onRate: (id: string, rating: "good" | "bad" | "unrated") => void;
  onToggleActive: (id: string, isActive: boolean) => void;
}) {
  const styleLabel = POSTING_STYLE_LABELS[agent.posting_style] || agent.posting_style;
  const topics =
    Array.isArray(agent.interested_topics)
      ? agent.interested_topics
      : [];

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "#fff",
          borderRadius: 12,
          padding: "24px 28px",
          maxWidth: 520,
          width: "90%",
          maxHeight: "80vh",
          overflow: "auto",
          boxShadow: "0 8px 32px rgba(0,0,0,0.2)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <h2 style={{ margin: 0, fontSize: 20 }}>{agent.name}</h2>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              fontSize: 20,
              cursor: "pointer",
              color: "#888",
            }}
          >
            ✕
          </button>
        </div>

        {/* Basic info */}
        <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse", marginBottom: 16 }}>
          <tbody>
            {[
              ["Age", `${agent.age}`],
              ["Gender", GENDER_LABEL[agent.gender] || agent.gender],
              ["Profession", agent.profession || "—"],
              ["MBTI", agent.mbti || "—"],
              ["Tone", agent.tone_style || "—"],
              ["Posting Style", styleLabel],
              ["Uses", `${agent.use_count}`],
              ["Registered", agent.created_at ? new Date(agent.created_at).toLocaleDateString("en-US") : "—"],
            ].map(([label, value]) => (
              <tr key={label} style={{ borderBottom: "1px solid #eee" }}>
                <td style={{ padding: "6px 8px", color: "#888", width: 100, verticalAlign: "top" }}>{label}</td>
                <td style={{ padding: "6px 8px" }}>{value}</td>
              </tr>
            ))}
            <tr style={{ borderBottom: "1px solid #eee" }}>
              <td style={{ padding: "6px 8px", color: "#888", width: 100, verticalAlign: "middle" }}>Status</td>
              <td style={{ padding: "6px 8px" }}>
                <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
                  <input
                    type="checkbox"
                    checked={agent.is_active === 1}
                    onChange={(e) => onToggleActive(agent.id, e.target.checked)}
                    onClick={(e) => e.stopPropagation()}
                  />
                  {agent.is_active === 1 ? "🟢 Active" : "💤 Inactive"}
                </label>
              </td>
            </tr>
          </tbody>
        </table>

        {/* Persona */}
        {agent.persona && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, color: "#888", marginBottom: 4 }}>Persona</div>
            <div
              style={{
                fontSize: 13,
                background: "#f5f5f5",
                padding: "8px 12px",
                borderRadius: 6,
                lineHeight: 1.6,
                whiteSpace: "pre-wrap",
              }}
            >
              {agent.persona.replace(/\|?\[/g, "\n[").replace(/\]/g, "]\n").trim()}
            </div>
          </div>
        )}

        {/* Bio */}
        {agent.bio && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, color: "#888", marginBottom: 4 }}>Bio</div>
            <div
              style={{
                fontSize: 13,
                background: "#f5f5f5",
                padding: "8px 12px",
                borderRadius: 6,
                lineHeight: 1.6,
              }}
            >
              {agent.bio}
            </div>
          </div>
        )}

        {/* Interested topics */}
        {topics.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 12, color: "#888", marginBottom: 4 }}>Interested Topics</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
              {topics.map((t, i) => (
                <span
                  key={i}
                  style={{
                    fontSize: 11,
                    background: "#e3f2fd",
                    color: "#1565c0",
                    padding: "2px 8px",
                    borderRadius: 10,
                  }}
                >
                  {t}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Rating buttons */}
        <div style={{ display: "flex", gap: 8, justifyContent: "center", paddingTop: 8, borderTop: "1px solid #eee" }}>
          <button
            onClick={() => onRate(agent.id, agent.rating === "good" ? "unrated" : "good")}
            style={{
              padding: "8px 24px",
              fontSize: 15,
              border: "2px solid #4caf50",
              borderRadius: 8,
              background: agent.rating === "good" ? "#4caf50" : "#fff",
              color: agent.rating === "good" ? "#fff" : "#4caf50",
              cursor: "pointer",
              fontWeight: "bold",
            }}
          >
            👍 Keep
          </button>
          <button
            onClick={() => onRate(agent.id, agent.rating === "bad" ? "unrated" : "bad")}
            style={{
              padding: "8px 24px",
              fontSize: 15,
              border: "2px solid #f44336",
              borderRadius: 8,
              background: agent.rating === "bad" ? "#f44336" : "#fff",
              color: agent.rating === "bad" ? "#fff" : "#f44336",
              cursor: "pointer",
              fontWeight: "bold",
            }}
          >
            👎 Replace
          </button>
        </div>
      </div>
    </div>
  );
}

function AgentCard({
  agent,
  onRate,
  onToggleActive,
  onClick,
}: {
  agent: PersistentAgent;
  onRate: (id: string, rating: "good" | "bad" | "unrated") => void;
  onToggleActive: (id: string, isActive: boolean) => void;
  onClick: () => void;
}) {
  const styleLabel = POSTING_STYLE_LABELS[agent.posting_style] || agent.posting_style;
  const isInactive = agent.is_active === 0;
  const ratingBg = isInactive
    ? "#f0f0f0"
    : agent.rating === "good" ? "#e8f5e9" : agent.rating === "bad" ? "#ffebee" : "#fff";
  const ratingBorder = isInactive
    ? "#bbb"
    : agent.rating === "good" ? "#4caf50" : agent.rating === "bad" ? "#f44336" : "#ddd";

  return (
    <div
      style={{
        border: `2px solid ${ratingBorder}`,
        borderRadius: 8,
        padding: "10px 12px",
        background: ratingBg,
        fontSize: 13,
        display: "flex",
        flexDirection: "column",
        gap: 4,
        opacity: isInactive ? 0.5 : 1,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <strong
          style={{ fontSize: 14, cursor: "pointer", color: "#1565c0", textDecoration: "underline" }}
          onClick={onClick}
        >
          {agent.name}
        </strong>
        <span style={{ fontSize: 11, color: "#888" }}>
          {agent.gender === "male" ? "♂" : agent.gender === "female" ? "♀" : "⚧"}{" "}
          {agent.age}
        </span>
      </div>
      <div style={{ color: "#555", fontSize: 12 }}>
        {agent.profession || "Unknown"} ・ {agent.mbti} ・ {styleLabel}
      </div>
      {agent.persona && (
        <div
          style={{
            fontSize: 11,
            color: "#666",
            background: isInactive ? "#e8e8e8" : agent.rating === "good" ? "#c8e6c9" : agent.rating === "bad" ? "#ffcdd2" : "#f9f9f9",
            padding: "4px 6px",
            borderRadius: 4,
            maxHeight: 48,
            overflow: "hidden",
          }}
        >
          {agent.persona.slice(0, 80)}{agent.persona.length > 80 ? "…" : ""}
        </div>
      )}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 4 }}>
        <label style={{ display: "flex", alignItems: "center", gap: 4, cursor: "pointer", fontSize: 12 }}>
          <input
            type="checkbox"
            checked={agent.is_active === 1}
            onChange={(e) => onToggleActive(agent.id, e.target.checked)}
            onClick={(e) => e.stopPropagation()}
          />
          {agent.is_active === 1 ? "🟢 Active" : "💤 Inactive"}
        </label>
        <span style={{ display: "flex", gap: 4 }}>
          <button
            onClick={() => onRate(agent.id, agent.rating === "good" ? "unrated" : "good")}
            style={{
              padding: "3px 10px",
              fontSize: 14,
              border: "1px solid #4caf50",
              borderRadius: 4,
              background: agent.rating === "good" ? "#4caf50" : "#fff",
              color: agent.rating === "good" ? "#fff" : "#4caf50",
              cursor: "pointer",
            }}
          >
            👍
          </button>
          <button
            onClick={() => onRate(agent.id, agent.rating === "bad" ? "unrated" : "bad")}
            style={{
              padding: "3px 10px",
              fontSize: 14,
              border: "1px solid #f44336",
              borderRadius: 4,
              background: agent.rating === "bad" ? "#f44336" : "#fff",
              color: agent.rating === "bad" ? "#fff" : "#f44336",
              cursor: "pointer",
            }}
          >
            👎
          </button>
        </span>
      </div>
    </div>
  );
}

export default function AgentsPage() {
  const [agents, setAgents] = useState<PersistentAgent[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<PersistentAgent | null>(null);
  const [filter, setFilter] = useState<"all" | "good" | "bad" | "unrated" | "active" | "inactive">("all");
  const [enhancing, setEnhancing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [showGenDialog, setShowGenDialog] = useState(false);
  const [genCount, setGenCount] = useState(3);

  const fetchAgents = async () => {
    try {
      const data = await api.getPersistentAgents();
      setAgents(data);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAgents();
  }, []);

  const handleRate = async (agentId: string, rating: "good" | "bad" | "unrated") => {
    try {
      await api.ratePersistentAgent(agentId, rating);
      setAgents((prev) => prev.map((a) => (a.id === agentId ? { ...a, rating } : a)));
      if (selected?.id === agentId) {
        setSelected((s) => (s ? { ...s, rating } : null));
      }
    } catch (e: any) {
      alert("Rating failed: " + e.message);
    }
  };

  const handleToggleActive = async (agentId: string, isActive: boolean) => {
    try {
      await api.toggleAgentActive(agentId, isActive);
      setAgents((prev) => prev.map((a) => a.id === agentId ? { ...a, is_active: isActive ? 1 : 0 } : a));
      if (selected?.id === agentId) {
        setSelected((s) => s ? { ...s, is_active: isActive ? 1 : 0 } : null);
      }
    } catch (e: any) {
      alert("Toggle failed: " + e.message);
    }
  };

  const handleBulkActivate = async () => {
    try {
      for (const a of filtered) {
        if (a.is_active !== 1) {
          await api.toggleAgentActive(a.id, true);
        }
      }
      await fetchAgents();
    } catch (e: any) {
      alert("Bulk activate failed: " + e.message);
    }
  };

  const handleBulkDeactivate = async () => {
    try {
      for (const a of filtered) {
        if (a.is_active !== 0) {
          await api.toggleAgentActive(a.id, false);
        }
      }
      await fetchAgents();
    } catch (e: any) {
      alert("Bulk deactivate failed: " + e.message);
    }
  };

  const filtered = filter === "all"
    ? agents
    : filter === "active"
    ? agents.filter((a) => a.is_active === 1)
    : filter === "inactive"
    ? agents.filter((a) => a.is_active === 0)
    : agents.filter((a) => a.rating === filter);
  const goodCount = agents.filter((a) => a.rating === "good").length;
  const badCount = agents.filter((a) => a.rating === "bad").length;
  const unratedCount = agents.filter((a) => a.rating === "unrated").length;
  const activeCount = agents.filter((a) => a.is_active === 1).length;
  const inactiveCount = agents.filter((a) => a.is_active === 0).length;

  return (
    <div>
      <div style={{ marginBottom: 12 }}>
        <Link href="/" style={{ fontSize: 13, color: "#1565c0" }}>← Back to Top</Link>
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
        <div className="ochch-page-title" style={{ margin: 0 }}>👥 Agent Stock ({agents.length})</div>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            className="ochch-btn"
            style={{
              padding: "6px 16px",
              fontSize: 13,
              background: generating ? "#888" : "#2196f3",
              borderColor: generating ? "#888" : "#2196f3",
              color: "#fff",
            }}
            disabled={generating}
            onClick={() => setShowGenDialog(true)}
          >
            {generating ? "⏳ Generating..." : "➕ Add Agents"}
          </button>
          <button
            className="ochch-btn"
            style={{
              padding: "6px 16px",
              fontSize: 13,
              background: enhancing ? "#888" : "#7c4dff",
              borderColor: enhancing ? "#888" : "#7c4dff",
              color: "#fff",
            }}
            disabled={enhancing}
            onClick={async () => {
              setEnhancing(true);
              try {
                const res = await api.enhancePersistentAgents();
                alert(`✨ Started enhancing personas for ${res.target_count} agents. This may take a few minutes.`);
                setTimeout(() => fetchAgents(), 30000);
              } catch (e: any) {
                alert("Enhancement failed: " + e.message);
              } finally {
                setEnhancing(false);
              }
            }}
          >
            {enhancing ? "⏳ Enhancing..." : "✨ Enhance Personas"}
          </button>
        </div>
      </div>

      {/* Add Agent Dialog */}
      {showGenDialog && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.5)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
          onClick={() => setShowGenDialog(false)}
        >
          <div
            style={{
              background: "#fff",
              borderRadius: 12,
              padding: "24px 28px",
              maxWidth: 360,
              width: "90%",
              boxShadow: "0 8px 32px rgba(0,0,0,0.2)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ margin: "0 0 16px", fontSize: 18 }}>➕ Add Agents</h3>
            <p style={{ fontSize: 13, color: "#666", marginBottom: 16 }}>
              Generate new agents via LLM and add them to the stock.
            </p>
            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 13, color: "#555", display: "block", marginBottom: 6 }}>
                Count to add
              </label>
              <input
                type="number"
                min={1}
                max={20}
                value={genCount}
                onChange={(e) => setGenCount(Math.max(1, Math.min(20, parseInt(e.target.value) || 1)))}
                style={{
                  width: "100%",
                  padding: "8px 12px",
                  fontSize: 16,
                  border: "2px solid #2196f3",
                  borderRadius: 8,
                  outline: "none",
                  textAlign: "center",
                  boxSizing: "border-box",
                }}
              />
              <div style={{ fontSize: 11, color: "#999", marginTop: 4 }}>1–20 (~30 sec per agent)</div>
            </div>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button
                className="ochch-btn ochch-btn-secondary"
                style={{ padding: "8px 20px", fontSize: 13 }}
                onClick={() => setShowGenDialog(false)}
              >
                Cancel
              </button>
              <button
                className="ochch-btn"
                style={{
                  padding: "8px 20px",
                  fontSize: 13,
                  background: "#2196f3",
                  borderColor: "#2196f3",
                  color: "#fff",
                }}
                onClick={async () => {
                  setShowGenDialog(false);
                  setGenerating(true);
                  try {
                    const res = await api.generatePersistentAgents(genCount);
                    alert(`➕ Started generating ${res.count} agents. Please wait for completion.`);
                    // Reload after generation completes (count × 30s + buffer)
                    const waitMs = Math.max(15000, genCount * 30000 + 5000);
                    setTimeout(() => fetchAgents(), waitMs);
                  } catch (e: any) {
                    alert("Generation failed: " + e.message);
                  } finally {
                    setGenerating(false);
                  }
                }}
              >
                Start Generation
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Filter */}
      <div style={{ display: "flex", gap: 6, marginBottom: 8, flexWrap: "wrap" }}>
        {([
          ["all", `All (${agents.length})`],
          ["active", `🟢 Active (${activeCount})`],
          ["inactive", `💤 Inactive (${inactiveCount})`],
          ["good", `👍 Keep (${goodCount})`],
          ["bad", `👎 Replace (${badCount})`],
          ["unrated", `Unrated (${unratedCount})`],
        ] as [string, string][]).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setFilter(key as any)}
            className={filter === key ? "ochch-btn" : "ochch-btn ochch-btn-secondary"}
            style={{ padding: "4px 14px", fontSize: 12 }}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Bulk operations */}
      <div style={{ display: "flex", gap: 6, marginBottom: 16, flexWrap: "wrap", alignItems: "center" }}>
        <span style={{ fontSize: 12, color: "#888" }}>Bulk:</span>
        <button
          className="ochch-btn"
          style={{ padding: "4px 14px", fontSize: 12, background: "#43a047", borderColor: "#43a047", color: "#fff" }}
          onClick={handleBulkActivate}
        >
          ✅ Activate All
        </button>
        <button
          className="ochch-btn ochch-btn-secondary"
          style={{ padding: "4px 14px", fontSize: 12 }}
          onClick={handleBulkDeactivate}
        >
          💤 Deactivate All
        </button>
      </div>

      {loading ? (
        <div style={{ padding: 20, color: "#888" }}>Loading<span className="loading-dots" /></div>
      ) : filtered.length === 0 ? (
        <div style={{ padding: 20, background: "#fff", border: "1px solid #ddd", color: "#888", textAlign: "center", borderRadius: 8 }}>
          {filter === "all"
            ? "No agents yet. Run a simulation and they will be stocked automatically."
            : "No agents match this filter."}
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 10 }}>
          {filtered.map((agent) => (
            <AgentCard
              key={agent.id}
              agent={agent}
              onRate={handleRate}
              onToggleActive={handleToggleActive}
              onClick={() => setSelected(agent)}
            />
          ))}
        </div>
      )}

      {/* Detail modal */}
      {selected && (
        <AgentDetailModal
          agent={selected}
          onClose={() => setSelected(null)}
          onRate={handleRate}
          onToggleActive={handleToggleActive}
        />
      )}
    </div>
  );
}
