/**
 * API client
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

export interface SimulationSummary {
  id: string;
  theme: string;
  created_at: string;
  status: string;
  board_count: number;
  total_posts: number;
  elapsed_seconds?: number | null;
}

export interface SeedDataInfo {
  og_image?: string;
  source_url?: string;
}

export interface SimulationStatus {
  id: string;
  theme: string;
  prompt: string;
  status: string;
  progress: number;
  round_current: number;
  round_total: number;
  agent_count: number;
  created_at: string;
  board_count: number;
  total_posts: number;
  elapsed_seconds?: number | null;
  seed_info?: SeedDataInfo | null;
}

export interface BoardInfo {
  id: string;
  simulation_id: string;
  name: string;
  emoji: string;
  description: string;
  thread_count: number;
  post_count: number;
}

export interface ThreadInfo {
  id: string;
  board_id: string;
  simulation_id: string;
  title: string;
  post_count: number;
  last_post_at: string | null;
  is_active: boolean;
}

export interface PostInfo {
  post_id: string;
  post_num: number;
  agent_name: string;
  username: string;
  content: string;
  reply_to: number | null;
  timestamp: string;
  emotion: string;
}

export interface ThreadDetail {
  thread_id: string;
  title: string;
  board_name: string;
  board_id: string;
  simulation_id: string;
  posts: PostInfo[];
}

export interface AgentInfo {
  agent_id: string;
  name: string;
  username: string;
  bio: string;
  persona: string;
  age: number;
  gender: string;
  mbti: string;
  tone_style: string;
  profession: string;
  interested_topics: string[];
  post_count: number;
  stance?: Record<string, string>;
  hidden_agenda?: string;
}

export interface PersistentAgent {
  id: string;
  name: string;
  username: string;
  bio: string;
  persona: string;
  age: number;
  gender: string;
  mbti: string;
  tone_style: string;
  profession: string;
  interested_topics: string[];
  posting_style: string;
  use_count: number;
  created_at: string;
  rating: "good" | "bad" | "unrated";
  is_active: number;  // 1=active, 0=inactive
}

export interface Board {
  id: string;
  name: string;
}

export interface PostIndexEntry {
  board_id: string;
  thread_id: string;
  board_name: string;
  post_num: number;
}

export interface ReportData {
  simulation_id: string;
  theme: string;
  summary: string;
  details: string;
  confidence: number;
  key_findings: string[];
  agent_positions: Record<string, string>;
  turning_points: string[];
  consensus: string;
  minority_views: string[];
  prediction: string;
  created_at: string;
  // Additional fields
  boards: Board[];
  posts_index: Record<string, PostIndexEntry>;
  stance_distribution: Record<string, number>;
  activity_by_round: number[];
  consensus_score: number;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, options);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

export const api = {
  // Simulations
  listSimulations: () => request<SimulationSummary[]>("/api/simulations"),
  getStatus: (id: string) =>
    request<SimulationStatus>(`/api/simulation/${id}/status`),
  deleteSimulation: (id: string) =>
    request<{ ok: boolean }>(`/api/simulation/${id}`, { method: "DELETE" }),
  pauseSimulation: (id: string) =>
    request<{ ok: boolean; previous_status: string }>(`/api/simulation/${id}/pause`, { method: "POST" }),
  resumeSimulation: (id: string) =>
    request<{ ok: boolean }>(`/api/simulation/${id}/resume`, { method: "POST" }),

  // Boards & threads
  getBoards: (simId: string) =>
    request<BoardInfo[]>(`/api/simulation/${simId}/boards`),
  getThreads: (simId: string, boardId: string) =>
    request<ThreadInfo[]>(`/api/simulation/${simId}/board/${boardId}/threads`),
  getThread: (simId: string, threadId: string) =>
    request<ThreadDetail>(`/api/simulation/${simId}/thread/${threadId}`),

  // Agents
  getAgents: (simId: string) =>
    request<AgentInfo[]>(`/api/simulation/${simId}/agents`),
  getAgent: (simId: string, agentId: string) =>
    request<AgentInfo>(`/api/simulation/${simId}/agent/${agentId}`),

  // Report
  getReport: (simId: string) =>
    request<ReportData>(`/api/simulation/${simId}/report`),

  // Question history
  getAskHistory: (simId: string) =>
    request<any[]>(`/api/simulation/${simId}/ask/history`),

  // Persistent agents
  getPersistentAgents: () =>
    request<PersistentAgent[]>("/api/agents/persistent"),
  ratePersistentAgent: (agentId: string, rating: "good" | "bad" | "unrated") =>
    request<{ ok: boolean }>(`/api/agents/persistent/${agentId}/rate?rating=${rating}`, { method: "POST" }),
  deletePersistentAgent: (agentId: string) =>
    request<{ ok: boolean }>(`/api/agents/persistent/${agentId}`, { method: "DELETE" }),
  enhancePersistentAgents: () =>
    request<{ ok: boolean; target_count?: number; message?: string }>("/api/agents/persistent/enhance", { method: "POST" }),
  generatePersistentAgents: (count: number) =>
    request<{ ok: boolean; count?: number; message?: string }>(`/api/agents/persistent/generate?count=${count}`, { method: "POST" }),
  toggleAgentActive: async (agentId: string, isActive: boolean) => {
    const res = await fetch(`${BASE_URL}/api/agents/persistent/${agentId}/active`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: isActive }),
    });
    return res.json();
  },
  getJikkyo: (simId: string) =>
    request<{ events: Array<{ id: number; event_type: string; lines: string[]; seq: number; created_at: string }> }>(`/api/simulation/${simId}/jikkyo`),

  // Seed extraction
  extractSeed: async (data: { url?: string; text?: string }) => {
    const res = await fetch(`${BASE_URL}/api/seed/extract`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error(`API error ${res.status}`);
    return res.json() as Promise<{
      theme: string;
      question: string;
      entities: string[];
      tone: string;
      background_context: string;
    }>;
  },


  // Agent chat
  chatWithAgent: async (simId: string, agentId: string, message: string) => {
    const res = await fetch(`${BASE_URL}/api/simulation/${simId}/agent/${agentId}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    if (!res.ok) throw new Error(`API error ${res.status}`);
    return res.json() as Promise<{
      agent_id: string;
      agent_name: string;
      reply: string;
      post_count: number;
    }>;
  },

  getAgentChatHistory: (simId: string, agentId: string) =>
    request<{ history: Array<{ id: string; role: string; content: string; created_at: string }> }>(
      `/api/simulation/${simId}/agent/${agentId}/chat/history`
    ),

  // GraphRAG
  getGraph: (simId: string) =>
    request<{
      nodes: Array<{ id: string; label: string; title: string; value: number; group: string }>;
      edges: Array<{ from: string; to: string; label: string; value: number; color: { color: string }; arrows: string; title: string; relationship_id?: string }>;
      stats: { most_influential: string | null; strongest_rivalry: { agents: string[]; intensity: number } | null };
    }>(`/api/simulation/${simId}/graph`),

  // Relationship Evidence
  getRelationshipEvidence: (simId: string, relationshipId: string) =>
    request<{ from_agent: string; to_agent: string; relation_type: string; evidence_text: string; evidence_posts: Array<{ agent_name: string; content: string; created_at: string }> }>(
      `/api/simulation/${simId}/relationship/${relationshipId}/evidence`
    ),

  // Agent Profile
  getAgentProfile: (simId: string, agentId: string) =>
    request<{ agent_id: string; name: string; mbti?: string; role?: string; tone_style?: string; personality_snippet?: string; post_count: number }>(
      `/api/simulation/${simId}/agent/${agentId}/profile`
    ),
};
