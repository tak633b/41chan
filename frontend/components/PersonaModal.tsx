"use client";

import { AgentInfo } from "@/lib/api";

interface Props {
  agent: AgentInfo | null;
  onClose: () => void;
}

const toneLabels: Record<string, string> = {
  authority: "Authority (professors, managers)",
  worker: "Worker (engineers, staff)",
  youth: "Youth (students, juniors)",
  outsider: "Outsider (contractors, temps)",
  lurker: "Lurker (observer)",
};

export default function PersonaModal({ agent, onClose }: Props) {
  if (!agent) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>
          ✕
        </button>
        <div className="modal-title">
          👤 {agent.name} ({agent.username})
        </div>

        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 8 }}>
          <span style={{ fontSize: 12 }}>
            Age: <strong>{agent.age}</strong>
          </span>
          <span style={{ fontSize: 12 }}>
            Gender: <strong>{agent.gender}</strong>
          </span>
          <span style={{ fontSize: 12 }}>
            MBTI: <strong>{agent.mbti}</strong>
          </span>
          <span style={{ fontSize: 12 }}>
            Posts: <strong>{agent.post_count}</strong>
          </span>
        </div>

        <div className="persona-field">
          <strong>Profession:</strong> {agent.profession}
        </div>
        <div className="persona-field">
          <strong>Tone Type:</strong>{" "}
          {toneLabels[agent.tone_style] || agent.tone_style}
        </div>
        {agent.stance && Object.keys(agent.stance).length > 0 && (
          <div className="persona-field">
            <strong>Stance:</strong>{" "}
            {typeof agent.stance === "object"
              ? (agent.stance as any).position || "-"
              : String(agent.stance)}
            <br />
            <span style={{ fontSize: 11, color: "#666" }}>
              {typeof agent.stance === "object"
                ? (agent.stance as any).reason || ""
                : ""}
            </span>
          </div>
        )}
        <div className="persona-field">
          <strong>Interests:</strong>{" "}
          {Array.isArray(agent.interested_topics)
            ? agent.interested_topics.join(", ")
            : agent.interested_topics}
        </div>
        <div className="persona-field">
          <strong>Bio:</strong>
          <div
            style={{
              background: "#f9f9f9",
              border: "1px solid #ddd",
              padding: "4px 6px",
              marginTop: 2,
              fontSize: 12,
              whiteSpace: "pre-wrap",
            }}
          >
            {agent.bio}
          </div>
        </div>
        <div className="persona-field">
          <strong>Persona:</strong>
          <div
            style={{
              background: "#f9f9f9",
              border: "1px solid #ddd",
              padding: "4px 6px",
              marginTop: 2,
              fontSize: 11,
              whiteSpace: "pre-wrap",
              maxHeight: 300,
              overflow: "auto",
              lineHeight: 1.7,
            }}
          >
            {agent.persona
              ? agent.persona
                  .replace(/\[/g, "\n[")
                  .replace(/^\n/, "")
                  .split("\n")
                  .map((line, i) => {
                    const m = line.match(/^(\[[^\]]+\])([\s\S]*)$/);
                    if (m) {
                      return (
                        <span key={i}>
                          <strong style={{ color: "#444" }}>{m[1]}</strong>
                          {m[2]}
                          {"\n"}
                        </span>
                      );
                    }
                    return <span key={i}>{line}{"\n"}</span>;
                  })
              : ""}
          </div>
        </div>
        {agent.hidden_agenda && (
          <div className="persona-field">
            <strong>Hidden Agenda:</strong>
            <div
              style={{
                background: "#fff8f8",
                border: "1px solid #f5c6cb",
                padding: "4px 6px",
                marginTop: 2,
                fontSize: 11,
                color: "#721c24",
              }}
            >
              {agent.hidden_agenda}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
