"use client";

import { AgentInfo, PostInfo } from "@/lib/api";

/** Same hash function as PostCard */
function hashName(name: string): number {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = ((hash << 5) - hash + name.charCodeAt(i)) | 0;
  }
  return hash >>> 0;
}
function isKotehan(agentName: string): boolean {
  return hashName(agentName) % 10 < 2;
}

interface BattleHeaderProps {
  agents: AgentInfo[];
  posts: PostInfo[];
  isActive: boolean;
  onAgentClick?: (agent: AgentInfo) => void;
}

/** tone_style → kaomoji (1-line ASCII art) */
function getCharFace(toneStyle: string): string {
  const style = (toneStyle || "").toLowerCase();
  if (style.includes("authority")) return "(｀ー´)ゞ";
  if (style.includes("worker")) return "(・д・)";
  if (style.includes("youth")) return "(*ﾟ∀ﾟ*)";
  if (style.includes("outsider")) return "(｀_´メ)";
  if (style.includes("lurker") || style.includes("rom")) return "(´-ω-｀)";
  return "(･ω･)";
}

export default function BattleHeader({
  agents,
  onAgentClick,
}: BattleHeaderProps) {
  return (
    <div className="battle-header">
      <div className="battle-header-label">▼ Anons in this thread</div>
      <div className="battle-residents">
        {agents.length === 0 ? (
          <div className="resident-empty">(no anons)</div>
        ) : (
          agents.map((agent) => (
            <button
              key={agent.agent_id}
              className="resident-icon"
              onClick={() => onAgentClick?.(agent)}
              title={agent.username}
            >
              <span className="resident-face">{getCharFace(agent.tone_style)}</span>
              <span className="resident-name">
                {isKotehan(agent.name) ? agent.name : "Anonymous"}
              </span>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
