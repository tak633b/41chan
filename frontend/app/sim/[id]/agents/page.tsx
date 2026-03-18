"use client";

import { useEffect, useState, use } from "react";
import Link from "next/link";
import { api, AgentInfo } from "@/lib/api";
import PersonaModal from "@/components/PersonaModal";

const toneLabels: Record<string, string> = {
  authority: "Authority",
  worker: "Worker",
  youth: "Youth",
  outsider: "Outsider",
  lurker: "Lurker",
};

export default function AgentsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id: simId } = use(params);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [selected, setSelected] = useState<AgentInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .getAgents(simId)
      .then(setAgents)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [simId]);

  if (loading) {
    return (
      <div style={{ padding: 20, color: "#888" }}>
        Loading<span className="loading-dots" />
      </div>
    );
  }

  return (
    <div>
      <div className="ochch-nav" style={{ marginBottom: 8 }}>
        <Link href="/">TOP</Link>
        <Link href={`/sim/${simId}`}>Simulation</Link>
        <span style={{ color: "#888" }}>▶ Agent List</span>
      </div>

      <div className="ochch-page-title">
        👥 Agent List ({agents.length})
      </div>

      {error && (
        <div
          style={{
            background: "#f8d7da",
            border: "1px solid #f5c6cb",
            padding: "6px 10px",
            color: "#721c24",
          }}
        >
          ⚠️ {error}
        </div>
      )}

      <table className="sim-list" style={{ fontSize: 12 }}>
        <thead>
          <tr>
            <th>Name</th>
            <th>ID</th>
            <th>Age</th>
            <th>Profession</th>
            <th>Tone</th>
            <th>MBTI</th>
            <th>Posts</th>
          </tr>
        </thead>
        <tbody>
          {agents.map((a) => (
            <tr key={a.agent_id}>
              <td>
                <span
                  className="post-name"
                  style={{ cursor: "pointer" }}
                  onClick={() => setSelected(a)}
                >
                  {a.name}
                </span>
              </td>
              <td style={{ color: "#888" }}>{a.username}</td>
              <td>{a.age}</td>
              <td>{a.profession}</td>
              <td>{toneLabels[a.tone_style] || a.tone_style}</td>
              <td>{a.mbti}</td>
              <td>{a.post_count}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {selected && (
        <PersonaModal agent={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
