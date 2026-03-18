"use client";

import { useEffect, useState, useRef, use } from "react";
import Link from "next/link";
import { api, ThreadDetail, PostInfo, AgentInfo } from "@/lib/api";
import PostCard from "@/components/PostCard";
import PersonaModal from "@/components/PersonaModal";
import BattleHeader from "@/components/BattleHeader";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

export default function ThreadPage({
  params,
}: {
  params: Promise<{ id: string; threadId: string }>;
}) {
  const { id: simId, threadId } = use(params);
  const [thread, setThread] = useState<ThreadDetail | null>(null);
  const [posts, setPosts] = useState<PostInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedAgent, setSelectedAgent] = useState<AgentInfo | null>(null);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [sseActive, setSseActive] = useState(false);
  const [newPostIds, setNewPostIds] = useState<Set<string>>(new Set());
  const [thinkingPosts, setThinkingPosts] = useState<Map<string, { agent_name: string; username: string; post_num: number }>>(new Map());
  const bottomRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  // Fetch thread data
  const loadThread = async () => {
    try {
      const t = await api.getThread(simId, threadId);
      setThread(t);
      setPosts(t.posts);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  // Fetch agents
  const loadAgents = async () => {
    try {
      const data = await api.getAgents(simId);
      setAgents(data);
    } catch {}
  };

  // SSE connection
  const connectSSE = () => {
    if (eventSourceRef.current) return;

    const es = new EventSource(`${BASE_URL}/api/simulation/${simId}/stream`);
    eventSourceRef.current = es;
    setSseActive(true);

    es.addEventListener("post_thinking", (e: MessageEvent) => {
      try {
        const d = JSON.parse(e.data);
        if (d.thread_id === threadId) {
          setThinkingPosts((prev) => {
            const next = new Map(prev);
            next.set(String(d.post_num), {
              agent_name: d.agent_name ?? "",
              username: d.username ?? "Anonymous",
              post_num: d.post_num,
            });
            return next;
          });
        }
      } catch {}
    });

    es.addEventListener("new_post", (e: MessageEvent) => {
      try {
        const d = JSON.parse(e.data);
        if (d.thread_id === threadId) {
          // Remove matching entry from thinkingPosts
          setThinkingPosts((prev) => {
            const next = new Map(prev);
            next.delete(String(d.post?.post_num));
            return next;
          });
          setPosts((prev) => {
            // Duplicate check
            if (prev.find((p) => p.post_id === d.post?.post_id)) {
              return prev;
            }
            return [...prev, d.post];
          });
          // Set new post flag → clear after 2 seconds
          const postId: string = d.post?.post_id;
          if (postId) {
            setNewPostIds((prev) => new Set(prev).add(postId));
            setTimeout(() => {
              setNewPostIds((prev) => {
                const next = new Set(prev);
                next.delete(postId);
                return next;
              });
            }, 2000);
          }
          // Auto-scroll
          setTimeout(
            () => bottomRef.current?.scrollIntoView({ behavior: "smooth" }),
            100
          );
        }
      } catch {}
    });

    es.addEventListener("sim_complete", () => {
      setSseActive(false);
      es.close();
      eventSourceRef.current = null;
    });

    es.addEventListener("close", () => {
      setSseActive(false);
      es.close();
      eventSourceRef.current = null;
    });

    es.onerror = () => {
      setSseActive(false);
      es.close();
      eventSourceRef.current = null;
    };
  };

  useEffect(() => {
    loadThread();
    loadAgents();
    connectSSE();

    return () => {
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
    };
  }, [simId, threadId]);

  const handleNameClick = (agentName: string) => {
    const a = agents.find((ag) => ag.name === agentName);
    if (a) setSelectedAgent(a);
  };

  if (loading) {
    return (
      <div style={{ padding: 20, color: "#888" }}>
        Loading<span className="loading-dots" />
      </div>
    );
  }

  if (error) {
    return (
      <div
        style={{
          background: "#f8d7da",
          border: "1px solid #f5c6cb",
          padding: "8px 12px",
          color: "#721c24",
        }}
      >
        ⚠️ {error}
      </div>
    );
  }

  return (
    <div>
      <div className="ochch-nav" style={{ marginBottom: 6 }}>
        <Link href="/">TOP</Link>
        <Link href={`/sim/${simId}`}>Simulation</Link>
        {thread?.board_id && (
          <Link href={`/sim/${simId}/board/${thread.board_id}`}>
            {thread?.board_name}
          </Link>
        )}
        <span style={{ color: "#888" }}>▶ Thread</span>
      </div>

      <div className="thread-header">
        {thread?.title}
        <span style={{ fontSize: 11, color: "#888", marginLeft: 8 }}>
          ({thread?.board_name})
        </span>
      </div>

      <BattleHeader
        agents={agents}
        posts={posts}
        isActive={sseActive}
        onAgentClick={(agent) => setSelectedAgent(agent)}
      />

      {sseActive && (
        <div
          style={{
            fontSize: 11,
            color: "#0c5460",
            background: "#d1ecf1",
            border: "1px solid #bee5eb",
            padding: "3px 8px",
            marginBottom: 6,
          }}
        >
          ⚡ Real-time updates active...
        </div>
      )}

      <div className="posts-container">
        {posts.length === 0 ? (
          <div
            style={{
              padding: 16,
              background: "#fff",
              border: "1px solid #ddd",
              color: "#888",
              textAlign: "center",
            }}
          >
            No posts yet
          </div>
        ) : (
          posts.map((p, idx) => (
            <PostCard
              key={p.post_id}
              post={p}
              allPosts={posts}
              onNameClick={handleNameClick}
              isNew={newPostIds.has(p.post_id)}
              isFirstPost={idx === 0}
              threadTitle={thread?.title}
            />
          ))
        )}
        {Array.from(thinkingPosts.values()).map((t) => (
          <div key={`thinking-${t.post_num}`} className="post-item post-thinking-placeholder">
            <div className="post-header">
              <span className="post-num">{t.post_num}</span>
              <span className="post-name" style={{ color: "#800000" }}>{t.username}</span>
            </div>
            <div className="post-body thinking-dots">Posting<span className="dot-anim">...</span></div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div style={{ margin: "8px 0", fontSize: 12, color: "#888" }}>
        Total posts: {posts.length}
      </div>

      <PersonaModal
        agent={selectedAgent}
        onClose={() => setSelectedAgent(null)}
      />
    </div>
  );
}
