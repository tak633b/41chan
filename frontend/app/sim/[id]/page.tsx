"use client";

import { useEffect, useState, useRef, use, useCallback } from "react";
import Link from "next/link";
import { api, SimulationStatus, BoardInfo } from "@/lib/api";

// ─── Type definitions ────────────────────────────────────
interface JikkyoPost {
  num: number;
  lines: string[];
  timestamp: string;
}

// ─── Utilities ───────────────────────────────────────────
function nowStr() {
  const d = new Date();
  return `${d.getFullYear()}/${String(d.getMonth() + 1).padStart(2, "0")}/${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function makeProgressBar(pct: number, width = 10): string {
  const filled = Math.round((pct / 100) * width);
  return "█".repeat(filled) + "░".repeat(width - filled);
}

// ─── Imageboard-style component ──────────────────────────
function JikkyoThread({ posts }: { posts: JikkyoPost[] }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [posts]);

  return (
    <div
      ref={containerRef}
      style={{
        background: "#EFEFEF",
        border: "1px solid #999",
        padding: "8px 4px",
        maxHeight: 420,
        overflowY: "auto",
        fontFamily: "monospace",
        fontSize: 12,
        lineHeight: 1.6,
      }}
    >
      {/* Thread title */}
      <div
        style={{
          background: "#800000",
          color: "#fff",
          padding: "4px 8px",
          fontWeight: "bold",
          marginBottom: 8,
          fontSize: 13,
        }}
      >
        🔮 Simulation Live Thread
      </div>

      {posts.map((p) => (
        <div
          key={p.num}
          style={{
            borderBottom: "1px dashed #ccc",
            padding: "4px 8px 6px",
          }}
        >
          {/* Post header */}
          <div style={{ color: "#008000", marginBottom: 2 }}>
            <span style={{ marginRight: 6, color: "#555" }}>{p.num}</span>
            <span style={{ color: "#000080", fontWeight: "bold" }}>
              Name: 41chan ★
            </span>
            <span style={{ color: "#808080", marginLeft: 8, fontSize: 11 }}>
              {p.timestamp}
            </span>
          </div>
          {/* Post body */}
          {p.lines.map((line, i) => (
            <div key={i} style={{ paddingLeft: 12, whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
              {line}
            </div>
          ))}
        </div>
      ))}

      {posts.length === 0 && (
        <div style={{ padding: "16px 8px", color: "#888", textAlign: "center" }}>
          Live thread preparing...
        </div>
      )}
    </div>
  );
}

function ProgressBar({ progress, status, createdAt }: { progress: number; status: string; createdAt?: string }) {
  const pct = Math.round(progress * 100);
  const labels: Record<string, string> = {
    initializing: "Initializing...",
    extracting: "Extracting entities...",
    generating_agents: "Generating agents...",
    generating_boards: "Generating boards...",
    simulating: "Simulating...",
    reporting: "Generating report...",
    completed: "Complete!",
    failed: "Failed",
  };

  // ETA calculation
  let etaText = "";
  if (createdAt && progress > 0.05 && progress < 1 && !["completed", "failed"].includes(status)) {
    const elapsed = (Date.now() - new Date(createdAt).getTime()) / 1000;
    const remaining = (elapsed / progress) * (1 - progress);
    if (remaining > 0 && remaining < 7200) {
      const mins = Math.floor(remaining / 60);
      const secs = Math.round(remaining % 60);
      etaText = mins > 0 ? `~${mins}m${secs}s left` : `~${secs}s left`;
    }
  }

  return (
    <div style={{ marginBottom: 4 }}>
      <div style={{ fontSize: 11, marginBottom: 2, color: "#555" }}>
        {labels[status] || status} — {pct}%{etaText ? ` (${etaText})` : ""}
      </div>
      <div className="progress-bar-container">
        <div className="progress-bar-fill" style={{ width: `${pct}%` }} />
        <span className="progress-bar-label">{pct}%</span>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const labels: Record<string, string> = {
    initializing: "Initializing",
    extracting: "Extracting",
    generating_agents: "Generating Agents",
    generating_boards: "Generating Boards",
    simulating: "Simulating",
    reporting: "Generating Report",
    completed: "Completed",
    failed: "Failed",
  };
  return (
    <span className={`status-badge status-${status}`}>
      {labels[status] || status}
    </span>
  );
}

// ─── vis-network graph (no SSR → dynamic import inside useEffect) ─
function VisGraph({ nodes, edges, onNodeClick, onEdgeClick }: {
  nodes: Array<{id: string; label: string; value?: number}>;
  edges: Array<{from: string; to: string; label: string; value?: number; color?: string; relationship_id?: string}>;
  onNodeClick: (nodeId: string, nodeLabel: string) => void;
  onEdgeClick?: (relationshipId: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<any>(null);

  useEffect(() => {
    if (!containerRef.current || nodes.length === 0) return;

    import("vis-network/standalone").then((vis: any) => {
      const Network = vis.Network;
      const DataSet = vis.DataSet;

      // Node size: log scale + cap to prevent oversizing
      const maxValue = Math.max(...nodes.map(n => n.value ?? 1), 1);
      const calcSize = (v: number) => {
        const normalized = Math.log1p(v) / Math.log1p(maxValue); // 0~1
        return 10 + normalized * 20; // min 10, max 30
      };

      const nodesData = new DataSet(
        nodes.map(n => ({
          id: n.id,
          label: n.label,
          size: calcSize(n.value ?? 1),
          font: { size: 13, color: "#333" },
          color: {
            background: "#e8f4f8",
            border: "#2980b9",
            highlight: { background: "#d5e8d4", border: "#82b366" },
          },
          shape: "dot",
        }))
      );

      const colorMap: Record<string, string> = {
        agree: "#27ae60", disagree: "#e74c3c", quote: "#2980b9", influence: "#f39c12",
      };
      const labelMap: Record<string, string> = {
        agree: "Agree", disagree: "Disagree", quote: "Quote", influence: "Influence",
      };
      const edgesData = new DataSet(
        edges.map((e, i) => ({
          id: i,
          from: e.from,
          to: e.to,
          label: labelMap[e.label] ?? e.label,
          color: { color: colorMap[e.label] ?? "#999", highlight: colorMap[e.label] ?? "#999" },
          width: Math.max(1, (e.value ?? 1) * 1.5),
          arrows: { to: { enabled: true, scaleFactor: 0.6 } },
          font: { size: 10, color: "#555", strokeWidth: 2, strokeColor: "#fff" },
          smooth: { enabled: true, type: "curvedCW", roundness: 0.2 },
          relationship_id: e.relationship_id ?? "",
        }))
      );

      const options = {
        layout: { improvedLayout: true },
        physics: {
          enabled: true,
          solver: "forceAtlas2Based",
          forceAtlas2Based: { gravitationalConstant: -50, springLength: 120 },
          stabilization: { iterations: 150 },
        },
        interaction: { hover: true, tooltipDelay: 200, zoomView: true, dragView: true },
        nodes: { borderWidth: 2 },
        edges: { selectionWidth: 3 },
      };

      if (networkRef.current) networkRef.current.destroy();
      networkRef.current = new Network(
        containerRef.current!,
        { nodes: nodesData, edges: edgesData },
        options
      );

      // Stop physics after stabilization → prevents layout shifting on click
      networkRef.current.once("stabilized", () => {
        networkRef.current?.setOptions({ physics: { enabled: false } });
      });

      networkRef.current.on("click", (params: any) => {
        if (params.edges.length > 0 && params.nodes.length === 0) {
          // Edge click
          const edgeId = params.edges[0];
          const edgeItem = edgesData.get(edgeId);
          if (edgeItem?.relationship_id && onEdgeClick) {
            onEdgeClick(edgeItem.relationship_id);
          }
        }
        if (params.nodes.length > 0) {
          const nodeId = params.nodes[0];
          const node = nodes.find(n => n.id === nodeId);
          if (node) onNodeClick(nodeId, node.label);
        }
      });
      networkRef.current.on("hoverNode", () => {
        if (containerRef.current) containerRef.current.style.cursor = "pointer";
      });
      networkRef.current.on("blurNode", () => {
        if (containerRef.current) containerRef.current.style.cursor = "default";
      });
      networkRef.current.on("hoverEdge", () => {
        if (containerRef.current) containerRef.current.style.cursor = "pointer";
      });
      networkRef.current.on("blurEdge", () => {
        if (containerRef.current) containerRef.current.style.cursor = "default";
      });
    });

    return () => {
      networkRef.current?.destroy();
      networkRef.current = null;
    };
  }, [nodes, edges]);

  return (
    <div
      ref={containerRef}
      style={{
        width: "100%", height: 420,
        border: "1px solid #ddd", background: "#fafafa", borderRadius: 4,
      }}
    />
  );
}

// ─── Main page ─────────────────────────────────────────────
export default function SimPage({ params }: { params: Promise<{ id: string }> }) {
  const { id: simId } = use(params);

  const [status, setStatus] = useState<SimulationStatus | null>(null);
  const [boards, setBoards] = useState<BoardInfo[]>([]);
  const [boardPostCounts, setBoardPostCounts] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [jikkyoPosts, setJikkyoPosts] = useState<JikkyoPost[]>([]);
  const [reportHighlight, setReportHighlight] = useState(false);
  const [sseConnected, setSseConnected] = useState(false);

  // Agent Chat
  const [chatAgent, setChatAgent] = useState<{id: string; name: string} | null>(null);
  const [chatMessages, setChatMessages] = useState<Array<{role: string; content: string}>>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [agents, setAgents] = useState<Array<{agent_id: string; name: string; post_count: number; tone_style: string}>>([]);

  // Graph tab
  const [activeTab, setActiveTab] = useState<"boards" | "graph">("boards");
  const [graphData, setGraphData] = useState<{nodes: any[]; edges: any[]; stats: any} | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);

  // Evidence Modal
  const [evidenceModal, setEvidenceModal] = useState<{
    relationshipId: string;
    fromAgent: string;
    toAgent: string;
    relationType: string;
    posts: Array<{agent_name: string; content: string; created_at: string}>;
  } | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);

  // Agent Profile
  const [chatAgentProfile, setChatAgentProfile] = useState<{
    agent_id: string; name: string; mbti?: string; role?: string;
    tone_style?: string; personality_snippet?: string; post_count: number;
  } | null>(null);

  // Counter refs (avoid re-renders)
  const jikkyoNumRef = useRef(0);
  const postCountRef = useRef(0);
  const agentCountRef = useRef(0);
  const boardCountRef = useRef(0);
  const completedRef = useRef(false);
  const sseRef = useRef<EventSource | null>(null);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  // ─── Live post helper ────────────────────────────────
  const addPost = useCallback((lines: string[]) => {
    jikkyoNumRef.current += 1;
    const num = jikkyoNumRef.current;
    setJikkyoPosts((prev) => [...prev, { num, lines, timestamp: nowStr() }]);
  }, []);

  // ─── Agent Chat ──────────────────────────────────────
  const openAgentChat = async (agentId: string, agentName: string) => {
    setChatAgent({ id: agentId, name: agentName });
    setChatAgentProfile(null);
    setChatMessages([]);
    setChatInput("");

    // Fetch profile asynchronously
    api.getAgentProfile(simId, agentId).then(profile => {
      setChatAgentProfile(profile);
    }).catch(() => {});

    try {
      const res = await api.getAgentChatHistory(simId, agentId);
      setChatMessages(res.history.map(h => ({ role: h.role, content: h.content })));
    } catch { /* ignore */ }
  };

  const sendChatMessage = async () => {
    if (!chatAgent || !chatInput.trim()) return;
    const msg = chatInput.trim();
    setChatInput("");
    setChatMessages(prev => [...prev, { role: "user", content: msg }]);
    setChatLoading(true);
    try {
      const res = await api.chatWithAgent(simId, chatAgent.id, msg);
      setChatMessages(prev => [...prev, { role: "agent", content: res.reply }]);
    } catch (e: any) {
      setChatMessages(prev => [...prev, { role: "agent", content: `(Error: ${e.message})` }]);
    } finally {
      setChatLoading(false);
    }
  };

  // ─── Graph ─────────────────────────────────────────────
  const loadGraph = async () => {
    setGraphLoading(true);
    try {
      const data = await api.getGraph(simId);
      setGraphData(data);
    } catch { /* ignore */ }
    setGraphLoading(false);
  };

  // ─── Edge Click → Evidence Modal ──────────────────────
  const handleEdgeClick = async (relationshipId: string) => {
    setEvidenceLoading(true);
    setEvidenceModal({ relationshipId, fromAgent: "", toAgent: "", relationType: "", posts: [] });
    try {
      const data = await api.getRelationshipEvidence(simId, relationshipId);
      setEvidenceModal({
        relationshipId,
        fromAgent: data.from_agent,
        toAgent: data.to_agent,
        relationType: data.relation_type,
        posts: data.evidence_posts,
      });
    } catch {
      setEvidenceModal(null);
    } finally {
      setEvidenceLoading(false);
    }
  };

  // ─── Polling (SSE fallback) ───────────────────────────
  const startPolling = useCallback(() => {
    if (pollingRef.current) return;
    pollingRef.current = setInterval(async () => {
      try {
        const s = await api.getStatus(simId);
        setStatus(s);
        if (s.status === "completed" || s.status === "failed") {
          clearInterval(pollingRef.current!);
          pollingRef.current = null;
          const b = await api.getBoards(simId);
          setBoards(b);
        } else {
          const b = await api.getBoards(simId);
          setBoards(b);
        }
      } catch {
        // ignore
      }
    }, 5000);
  }, [simId]);

  // ─── SSE connection ───────────────────────────────────
  // ─── Restore live log from DB on initial page load ───
  useEffect(() => {
    api.getJikkyo(simId).then((res) => {
      if (res.events && res.events.length > 0) {
        const restored = res.events.map((ev, i) => ({
          num: ev.seq || i + 1,
          lines: ev.lines,
          timestamp: new Date(ev.created_at).toLocaleString("en-US", {
            year: "numeric", month: "2-digit", day: "2-digit",
            hour: "2-digit", minute: "2-digit",
          }).replace(/\//g, "/"),
        }));
        setJikkyoPosts(restored);
        jikkyoNumRef.current = Math.max(...res.events.map((e) => e.seq || 0), 0);
      }
    }).catch(() => {});
  }, [simId]);

  useEffect(() => {
    const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

    const connectSSE = () => {
      if (completedRef.current) return;

      const es = new EventSource(`${BASE_URL}/api/simulation/${simId}/stream`);
      sseRef.current = es;

      es.onopen = () => {
        setSseConnected(true);
        // Keep polling active while SSE is connected (fallback if SSE events are dropped)
        // Just extend the polling interval
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
        startPolling();
      };

      es.onerror = () => {
        setSseConnected(false);
        es.close();
        sseRef.current = null;
        if (!completedRef.current) {
          // Start fallback polling
          startPolling();
          // Attempt reconnect after 5 seconds
          setTimeout(() => {
            if (!completedRef.current) connectSSE();
          }, 5000);
        }
      };

      // ─── SSE event handlers ────────────────────────────

      es.addEventListener("status_update", (e: MessageEvent) => {
        try {
          const d = JSON.parse(e.data);
          setStatus((prev) =>
            prev
              ? { ...prev, status: d.status, progress: d.progress, theme: d.theme ?? d.prompt ?? prev.theme, agent_count: d.agent_count ?? prev.agent_count, board_count: d.board_count ?? prev.board_count, total_posts: d.total_posts ?? prev.total_posts }
              : null
          );
          postCountRef.current = d.total_posts ?? postCountRef.current;
        } catch {}
      });

      es.addEventListener("new_agent", (e: MessageEvent) => {
        try {
          const d = JSON.parse(e.data);
          agentCountRef.current += 1;
          const n = agentCountRef.current;
          if (n === 1) {
            addPost(["( ﾟ∀ﾟ) Summoning agents..."]);
          }
          addPost([
            `NEW━━━(ﾟ∀ﾟ)━━━!! Anon #${n}`,
            `"Anon${String(n).padStart(2, "0")} (${d.role ?? "?"})"`,
          ].filter(Boolean));
        } catch {}
      });

      es.addEventListener("board_created", (e: MessageEvent) => {
        try {
          const d = JSON.parse(e.data);
          boardCountRef.current += 1;
          const boardName = d.name ?? d.board_name ?? "Unknown";
          if (boardCountRef.current === 1) {
            addPost(["Creating boards..."]);
          }
          addPost([`📋 ${boardName} NEW━(ﾟ∀ﾟ)━!`, d.description ? `(${d.description.slice(0, 30)})` : ""].filter(Boolean));
          // Add board card
          setBoards((prev) => {
            const exists = prev.some((b) => b.id === d.board_id);
            if (exists) return prev;
            return [
              ...prev,
              {
                id: d.board_id,
                simulation_id: simId,
                name: boardName,
                emoji: d.emoji ?? "📋",
                description: d.description ?? "",
                thread_count: 0,
                post_count: 0,
              },
            ];
          });
        } catch {}
      });

      es.addEventListener("round_start", (e: MessageEvent) => {
        try {
          const d = JSON.parse(e.data);
          const boardName = d.board ?? d.board_name ?? "Unknown";
          addPost([
            `[BREAKING] Battle begins on /${boardName}/`,
            d.thread_title ? `Thread: ${d.thread_title}` : `Round ${d.round_num} Start!`,
          ].filter(Boolean));
        } catch {}
      });

      let postSampleCounter = 0;
      es.addEventListener("new_post", (e: MessageEvent) => {
        try {
          const d = JSON.parse(e.data);
          postCountRef.current += 1;
          postSampleCounter += 1;

          // Real-time update of board post counts
          setBoardPostCounts((prev) => ({
            ...prev,
            [d.board_id]: (prev[d.board_id] ?? 0) + 1,
          }));

          // Sample one post every 5 posts
          if (postSampleCounter % 5 === 0) {
            const post = d.post ?? {};
            const agentName = post.agent_name ?? d.agent_name ?? "?";
            const content = post.content ?? d.content ?? "";
            const preview = content.slice(0, 30);
            addPost([
              `New post━(ﾟ∀ﾟ)━!`,
              `${agentName}: "${preview}${content.length > 30 ? "..." : ""}"`,
            ]);
          }

          // Show progress every 10 posts
          if (postSampleCounter % 10 === 0) {
            setStatus((prev) => {
              if (!prev) return prev;
              const pct = Math.round(prev.progress * 100);
              const bar = makeProgressBar(pct);
              addPost([
                "━━━ Progress ━━━━━━━━━━",
                `${bar} ${pct}%`,
                `Boards: ${prev.board_count} | Posts: ${postCountRef.current}`,
              ]);
              return prev;
            });
          }
        } catch {}
      });

      es.addEventListener("round_complete", (e: MessageEvent) => {
        try {
          const d = JSON.parse(e.data);
          const boardName = d.board ?? d.board_name ?? "Unknown";
          addPost([
            `/${boardName}/ Round ${d.round_num} complete!`,
            `${d.post_count} posts of heated debate`,
          ]);
        } catch {}
      });

      es.addEventListener("report_ready", (_e: MessageEvent) => {
        addPost(["Generating report... Analysis agent is hard at work"]);
      });

      es.addEventListener("sim_complete", (e: MessageEvent) => {
        try {
          const d = JSON.parse(e.data);
          completedRef.current = true;
          es.close();
          setSseConnected(false);

          const duration =
            typeof d.duration === "number"
              ? `${Math.round(d.duration / 60)}m${Math.round(d.duration % 60)}s`
              : String(d.duration ?? "?");

          addPost([
            "＿人人人人人人人人人＿",
            "＞ SIMULATION COMPLETE ＜",
            "￣Y^Y^Y^Y^Y^Y^Y^Y^￣",
            `Total posts: ${d.total_posts ?? postCountRef.current} | Duration: ${duration}`,
          ]);

          setStatus((prev) =>
            prev ? { ...prev, status: "completed", progress: 1, total_posts: d.total_posts ?? prev.total_posts } : prev
          );

          // After 3 seconds: highlight report button & auto-load graph
          setTimeout(() => { setReportHighlight(true); loadGraph(); }, 3000);

          // Final board update
          api.getBoards(simId).then(setBoards).catch(() => {});
        } catch {}
      });


      es.addEventListener("error", (e: MessageEvent) => {
        try {
          const d = JSON.parse(e.data);
          addPost([
            "(´；ω；`) An error occurred...",
            d.message ?? "Unknown error",
          ]);
          setError(d.message ?? "Unknown error");
          setStatus((prev) => (prev ? { ...prev, status: "failed" } : prev));
        } catch {}
      });
    };

    // ─── Initial data fetch ──────────────────────────
    (async () => {
      try {
        const [s, b] = await Promise.all([
          api.getStatus(simId),
          api.getBoards(simId),
        ]);
        setStatus(s);
        setBoards(b);
        postCountRef.current = s.total_posts;
        agentCountRef.current = s.agent_count;

        // Initial live post
        const topicName = s.theme || s.prompt || simId.slice(0, 8);
        addPost([
          "Simulation starting",
          `Topic: "${topicName}"`,
        ]);

        if (s.status === "initializing" || s.status === "extracting") {
          addPost(["Extracting entities... please wait"]);
        }

        // Fetch agent list
        if (s.agent_count > 0) {
          api.getAgents(simId).then((agentsList) => {
            setAgents(agentsList.map((a: any) => ({
              agent_id: a.agent_id,
              name: a.name,
              post_count: a.post_count,
              tone_style: a.tone_style,
            })));
          }).catch(() => {});
        }

        if (s.status === "completed" || s.status === "failed") {
          completedRef.current = true;
          if (s.status === "completed") {
            addPost([
              "＿人人人人人人人人人＿",
              "＞ SIMULATION COMPLETE (already fetched) ＜",
              "￣Y^Y^Y^Y^Y^Y^Y^Y^￣",
              `Total posts: ${s.total_posts}`,
            ]);
            setReportHighlight(true);
            loadGraph();
          }
        } else {
          // Start SSE connection
          connectSSE();
        }
      } catch (e: any) {
        setError(e.message);
        // Attempt SSE connection
        connectSSE();
      } finally {
        setLoading(false);
      }
    })();

    return () => {
      sseRef.current?.close();
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [simId]);

  // ─── Loading display ─────────────────────────────────
  if (loading) {
    return (
      <div style={{ padding: 20, color: "#888" }}>
        Loading<span className="loading-dots" />
      </div>
    );
  }

  // ─── JSX ───────────────────────────────────────────
  return (
    <div>
      <div className="ochch-page-title">
        🔮 {status?.theme || simId.slice(0, 8)}
      </div>

      {/* Status bar */}
      <div
        style={{
          background: "#fff",
          border: "1px solid #ddd",
          padding: "6px 10px",
          marginBottom: 10,
          fontSize: 12,
        }}
      >
        <div style={{ display: "flex", gap: 14, flexWrap: "wrap", alignItems: "center" }}>
          <span>
            Status: <StatusBadge status={status?.status || ""} />
          </span>
          <span>Agents: {status?.agent_count ?? 0}</span>
          <span>Boards: {status?.board_count ?? 0}</span>
          <span>Total Posts: {status?.total_posts ?? 0}</span>
          {status?.elapsed_seconds != null && status.elapsed_seconds > 0 && (status.status === "completed" || status.status === "failed") && (
            <span style={{ color: "#666" }}>
              ⏱️ {status.elapsed_seconds >= 60
                ? `${Math.floor(status.elapsed_seconds / 60)}m${Math.round(status.elapsed_seconds % 60)}s`
                : `${Math.round(status.elapsed_seconds)}s`}
            </span>
          )}
          {sseConnected && (
            <span style={{ color: "#090", fontSize: 11 }}>● SSE connected</span>
          )}
          {!sseConnected && !completedRef.current && (
            <span style={{ color: "#888", fontSize: 11 }}>○ Polling</span>
          )}
        </div>
      </div>

      {/* Error display */}
      {error && (
        <div
          style={{
            background: "#f8d7da",
            border: "1px solid #f5c6cb",
            padding: "6px 10px",
            color: "#721c24",
            marginBottom: 10,
            fontSize: 12,
          }}
        >
          ⚠️ {error}
        </div>
      )}

      {/* Live thread */}
      <div style={{ marginBottom: 10 }}>
        <JikkyoThread posts={jikkyoPosts} />
      </div>

      {/* Progress bar */}
      {status && status.status !== "completed" && status.status !== "failed" && (
        <div
          style={{
            background: "#fff",
            border: "1px solid #ddd",
            padding: "6px 10px",
            marginBottom: 10,
          }}
        >
          <ProgressBar progress={status.progress} status={status.status} createdAt={status.created_at} />
        </div>
      )}

      {/* Post-completion buttons */}
      {status?.status === "completed" && (
        <div
          style={{
            display: "flex",
            gap: 8,
            marginBottom: 12,
            padding: "8px 0",
          }}
        >
          <Link href={`/sim/${simId}/report`}>
            <button
              className="ochch-btn"
              style={{
                fontSize: 13,
                padding: "5px 14px",
                ...(reportHighlight
                  ? {
                      background: "#800000",
                      color: "#fff",
                      boxShadow: "0 0 8px rgba(128,0,0,0.5)",
                      animation: "pulse 1s infinite",
                    }
                  : {}),
              }}
            >
              📊 View Report
            </button>
          </Link>
          <Link href={`/sim/${simId}/ask`}>
            <button
              className="ochch-btn ochch-btn-secondary"
              style={{ fontSize: 13, padding: "5px 14px" }}
            >
              ❓ Ask Agents
            </button>
          </Link>
        </div>
      )}

      {/* Catalog link */}
      <div style={{ marginBottom: 8, fontSize: 12 }}>
        [<Link href={`/sim/${simId}/catalog`} style={{ color: "#0000ee" }}>Catalog</Link>]
      </div>

      {/* Boards */}
      {(
      <>
      <div style={{ marginBottom: 8, fontWeight: "bold", fontSize: 14 }}>
        📋 Boards
      </div>

      {boards.length === 0 ? (
        <div
          style={{
            padding: 16,
            background: "#fff",
            border: "1px solid #ddd",
            color: "#888",
            textAlign: "center",
            fontSize: 12,
          }}
        >
          {status?.status === "completed" || status?.status === "failed"
            ? "No boards"
            : "Generating boards..."}
        </div>
      ) : (
        <div className="board-grid">
          {boards.map((b) => {
            const realtimeCount = boardPostCounts[b.id] ?? 0;
            const displayCount = b.post_count + realtimeCount;
            return (
              <Link
                key={b.id}
                href={`/sim/${simId}/board/${b.id}`}
                style={{ textDecoration: "none" }}
              >
                <div className="board-card">
                  <div className="board-card-title">
                    {b.emoji} {b.name}
                  </div>
                  <div className="board-card-desc">{b.description}</div>
                  <div className="board-card-stats">
                    Threads: {b.thread_count} / Posts: {displayCount}
                    {realtimeCount > 0 && (
                      <span style={{ color: "#c00", fontSize: 10, marginLeft: 4 }}>
                        (+{realtimeCount})
                      </span>
                    )}
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      )}
      </>
      )}


      {/* ===== Relationship graph (shown after completion) ===== */}
      {status?.status === "completed" && (
        <div style={{ marginTop: 20 }}>
        <div style={{ marginBottom: 8, fontWeight: "bold", fontSize: 14 }}>🕸️ Relationship Graph</div>
        <div style={{
          background: "#fff", border: "1px solid #ddd",
          padding: 16, minHeight: 300,
        }}>
          {graphLoading ? (
            <div style={{ textAlign: "center", color: "#888", padding: 40 }}>Loading graph...</div>
          ) : graphData ? (
            <div>
              {/* Stats */}
              {graphData.stats && (
                <div style={{ marginBottom: 10, fontSize: 12, lineHeight: 1.8, background: "#f9f9f9", padding: "8px 12px", border: "1px solid #eee" }}>
                  {graphData.stats.most_influential && (
                    <div>👑 <strong>Most influential:</strong> {graphData.stats.most_influential}</div>
                  )}
                  {graphData.stats.strongest_rivalry && (
                    <div>⚔️ <strong>Strongest rivalry:</strong> {graphData.stats.strongest_rivalry.agents.join(" vs ")} (intensity: {graphData.stats.strongest_rivalry.intensity.toFixed(1)})</div>
                  )}
                </div>
              )}
              {/* Legend */}
              <div style={{ fontSize: 11, marginBottom: 8, display: "flex", gap: 16, color: "#555" }}>
                <span style={{ color: "#27ae60" }}>● Agree</span>
                <span style={{ color: "#e74c3c" }}>● Disagree</span>
                <span style={{ color: "#2980b9" }}>● Quote</span>
                <span style={{ color: "#f39c12" }}>● Influence</span>
                <span style={{ color: "#888", fontSize: 10 }}>Node=chat / Edge=show evidence</span>
              </div>
              {graphData.edges.length === 0 ? (
                <div style={{ textAlign: "center", color: "#888", padding: 20 }}>No relationship data yet</div>
              ) : (
                <VisGraph
                  nodes={graphData.nodes.map((n: any) => ({
                    id: n.id,
                    label: n.label,
                    value: n.value,
                  }))}
                  edges={graphData.edges.map((e: any) => ({
                    from: e.from,
                    to: e.to,
                    label: e.label,
                    value: e.value,
                    relationship_id: e.relationship_id,
                  }))}
                  onNodeClick={(nodeId, nodeLabel) => {
                    const agent = agents.find(a => a.agent_id === nodeId || a.name === nodeLabel);
                    if (agent) openAgentChat(agent.agent_id, agent.name);
                    else openAgentChat(nodeId, nodeLabel);
                  }}
                  onEdgeClick={handleEdgeClick}
                />
              )}
              {/* Edge count */}
              <div style={{ fontSize: 11, color: "#888", marginTop: 8, textAlign: "right" }}>
                Relationships: {graphData.edges.length} / Agents: {graphData.nodes.length}
              </div>
            </div>
          ) : (
            <div style={{ textAlign: "center", color: "#888", padding: 40 }}>
              <button className="ochch-btn" onClick={loadGraph}>Load Graph</button>
            </div>
          )}
        </div>
        </div>
      )}

      {/* ===== Agent Chat Modal ===== */}
      {chatAgent && (
        <div style={{
          position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
          background: "rgba(0,0,0,0.5)", zIndex: 1000,
          display: "flex", justifyContent: "center", alignItems: "center",
        }} onClick={() => setChatAgent(null)}>
          <div
            style={{
              background: "#fff", border: "2px solid #800000", width: 480, maxHeight: "80vh",
              display: "flex", flexDirection: "column",
            }}
            onClick={e => e.stopPropagation()}
          >
            {/* Header */}
            <div style={{
              background: "#800000", color: "#fff", padding: "8px 12px",
              display: "flex", justifyContent: "space-between", alignItems: "center",
            }}>
              <span style={{ fontWeight: "bold" }}>💬 Chat with {chatAgent.name}</span>
              <button onClick={() => setChatAgent(null)} style={{ color: "#fff", background: "none", border: "none", cursor: "pointer", fontSize: 16 }}>✕</button>
            </div>
            {/* Profile Section */}
            {chatAgentProfile && (
              <div style={{
                background: "#f9f9f9", borderBottom: "1px solid #ddd",
                padding: "8px 12px", fontSize: 11,
              }}>
                <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-start" }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <div style={{
                      width: 36, height: 36, background: "#800000", color: "#fff",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      fontSize: 16, borderRadius: 2, flexShrink: 0,
                    }}>
                      {chatAgentProfile.name.slice(0, 1)}
                    </div>
                    <div>
                      <div style={{ fontWeight: "bold", fontSize: 13 }}>{chatAgentProfile.name}</div>
                      <div style={{ color: "#555", fontSize: 10 }}>
                        {chatAgentProfile.mbti && <span style={{ background: "#e8f4f8", padding: "1px 5px", borderRadius: 3, marginRight: 4 }}>{chatAgentProfile.mbti}</span>}
                        {chatAgentProfile.role && <span style={{ color: "#666" }}>{chatAgentProfile.role}</span>}
                      </div>
                    </div>
                  </div>
                  <div style={{ color: "#666", lineHeight: 1.8 }}>
                    {chatAgentProfile.tone_style && <div>🎭 {chatAgentProfile.tone_style}</div>}
                    <div>💬 {chatAgentProfile.post_count} posts</div>
                  </div>
                </div>
                {chatAgentProfile.personality_snippet && (
                  <div style={{
                    marginTop: 6, padding: "4px 8px", background: "#fff",
                    border: "1px solid #eee", color: "#555", lineHeight: 1.5,
                    fontSize: 11, fontStyle: "italic",
                    maxHeight: 60, overflowY: "auto",
                  }}>
                    {chatAgentProfile.personality_snippet.slice(0, 200)}
                    {chatAgentProfile.personality_snippet.length > 200 ? "..." : ""}
                  </div>
                )}
              </div>
            )}
            {/* Messages */}
            <div style={{ flex: 1, overflowY: "auto", padding: 12, minHeight: 200, maxHeight: 400 }}>
              {chatMessages.length === 0 && (
                <div style={{ color: "#888", textAlign: "center", padding: 20, fontSize: 12 }}>
                  Ask this agent something
                </div>
              )}
              {chatMessages.map((m, i) => (
                <div key={i} style={{
                  marginBottom: 8, display: "flex",
                  justifyContent: m.role === "user" ? "flex-end" : "flex-start",
                }}>
                  <div style={{
                    maxWidth: "80%", padding: "6px 10px", fontSize: 12, lineHeight: 1.6,
                    borderRadius: 8,
                    background: m.role === "user" ? "#e3f2fd" : "#f5f5f5",
                    border: m.role === "user" ? "1px solid #90caf9" : "1px solid #ddd",
                  }}>
                    <div style={{ fontSize: 10, color: "#888", marginBottom: 2 }}>
                      {m.role === "user" ? "You" : chatAgent.name}
                    </div>
                    {m.content}
                  </div>
                </div>
              ))}
              {chatLoading && (
                <div style={{ color: "#888", fontSize: 12, padding: 4 }}>
                  {chatAgent.name} is thinking...
                </div>
              )}
            </div>
            {/* Input */}
            <div style={{ borderTop: "1px solid #ddd", padding: 8, display: "flex", gap: 6 }}>
              <input
                type="text"
                value={chatInput}
                onChange={e => setChatInput(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChatMessage(); } }}
                placeholder="Enter your question..."
                style={{ flex: 1, fontSize: 12, padding: "4px 8px" }}
                disabled={chatLoading}
              />
              <button
                className="ochch-btn"
                onClick={sendChatMessage}
                disabled={chatLoading || !chatInput.trim()}
                style={{ fontSize: 12, padding: "4px 10px" }}
              >
                Send
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ===== Evidence Modal ===== */}
      {evidenceModal && (
        <div style={{
          position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
          background: "rgba(0,0,0,0.5)", zIndex: 1100,
          display: "flex", justifyContent: "center", alignItems: "center",
        }} onClick={() => setEvidenceModal(null)}>
          <div style={{
            background: "#fff", border: "2px solid #800000", width: 520, maxHeight: "75vh",
            display: "flex", flexDirection: "column",
          }} onClick={e => e.stopPropagation()}>
            <div style={{
              background: "#800000", color: "#fff", padding: "8px 12px",
              display: "flex", justifyContent: "space-between", alignItems: "center",
            }}>
              <span style={{ fontWeight: "bold" }}>
                {evidenceModal.fromAgent} → {evidenceModal.toAgent} (
                {({ agree: "Agree", disagree: "Disagree", quote: "Quote", influence: "Influence" } as Record<string, string>)[evidenceModal.relationType] ?? evidenceModal.relationType}
                ) Evidence
              </span>
              <button onClick={() => setEvidenceModal(null)} style={{ color: "#fff", background: "none", border: "none", cursor: "pointer", fontSize: 16 }}>✕</button>
            </div>
            <div style={{ flex: 1, overflowY: "auto", padding: 12 }}>
              {evidenceLoading ? (
                <div style={{ textAlign: "center", color: "#888", padding: 20 }}>Loading...</div>
              ) : evidenceModal.posts.length === 0 ? (
                <div style={{ textAlign: "center", color: "#888", padding: 20 }}>No evidence data</div>
              ) : (
                evidenceModal.posts.map((p, i) => (
                  <div key={i} style={{
                    background: "#EFEFEF", border: "1px solid #999", padding: "8px 10px",
                    marginBottom: 8, fontFamily: "monospace", fontSize: 12,
                  }}>
                    <div style={{ color: "#000080", fontWeight: "bold", marginBottom: 4 }}>
                      {p.agent_name}
                      <span style={{ color: "#808080", fontWeight: "normal", marginLeft: 8, fontSize: 11 }}>
                        {new Date(p.created_at).toLocaleString("en-US")}
                      </span>
                    </div>
                    <div style={{ whiteSpace: "pre-wrap", wordBreak: "break-all", paddingLeft: 8, lineHeight: 1.6 }}>
                      {p.content}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* Agent list (with chat buttons) */}
      {status?.status === "completed" && agents.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontWeight: "bold", fontSize: 13, marginBottom: 6 }}>👥 Agents</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {agents.map(a => (
              <button
                key={a.agent_id}
                onClick={() => openAgentChat(a.agent_id, a.name)}
                style={{
                  fontSize: 11, padding: "4px 10px", cursor: "pointer",
                  border: "1px solid #ccc", background: "#fff", borderRadius: 4,
                }}
              >
                💬 {a.name} ({a.post_count} posts)
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Agent list link */}
      <div style={{ marginTop: 16, fontSize: 12 }}>
        <Link href={`/sim/${simId}/agents`} style={{ color: "#0000ee" }}>
          👥 View all agents
        </Link>
      </div>

      {/* Pulse animation */}
      <style>{`
        @keyframes pulse {
          0%   { box-shadow: 0 0 6px rgba(128,0,0,0.4); }
          50%  { box-shadow: 0 0 14px rgba(128,0,0,0.8); }
          100% { box-shadow: 0 0 6px rgba(128,0,0,0.4); }
        }
      `}</style>
    </div>
  );
}
