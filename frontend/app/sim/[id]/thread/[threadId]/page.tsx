"use client";

import { useEffect, useState, useRef, use } from "react";
import Link from "next/link";
import { api, ThreadDetail, PostInfo, AgentInfo, SimulationStatus } from "@/lib/api";
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
  const [ogImage, setOgImage] = useState<string>("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

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

  const loadAgents = async () => {
    try {
      const data = await api.getAgents(simId);
      setAgents(data);
    } catch {}
  };

  const loadSimStatus = async () => {
    try {
      const status = await api.getStatus(simId);
      if (status.seed_info?.og_image) {
        setOgImage(status.seed_info.og_image);
      }
    } catch {}
  };

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
          setThinkingPosts((prev) => {
            const next = new Map(prev);
            next.delete(String(d.post?.post_num));
            return next;
          });
          setPosts((prev) => {
            if (prev.find((p) => p.post_id === d.post?.post_id)) {
              return prev;
            }
            return [...prev, d.post];
          });
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
    loadSimStatus();
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
      <div style={{ padding: 20, color: "#707070" }}>
        Loading<span className="loading-dots" />
      </div>
    );
  }

  if (error) {
    return (
      <div
        style={{
          background: "#d6daf0",
          border: "1px solid #b7c5d9",
          padding: "8px 12px",
          color: "#d00000",
          fontSize: "9pt",
        }}
      >
        {error}
      </div>
    );
  }

  return (
    <div style={{ padding: "0 20px" }}>
      {/* Navigation */}
      <div className="ochch-nav" style={{ marginBottom: 6 }}>
        [<Link href="/">Home</Link>]{" "}
        [<Link href={`/sim/${simId}`}>Simulation</Link>]{" "}
        {thread?.board_id && (
          <>
            [<Link href={`/sim/${simId}/board/${thread.board_id}`}>
              {thread?.board_name}
            </Link>]{" "}
          </>
        )}
      </div>

      {/* Thread title */}
      <div className="thread-header">
        {thread?.title}
        <span style={{ fontSize: "9pt", color: "#707070", marginLeft: 8, fontWeight: "normal" }}>
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
            fontSize: "9pt",
            color: "#117743",
            background: "#d6daf0",
            border: "1px solid #b7c5d9",
            padding: "3px 8px",
            marginBottom: 6,
          }}
        >
          Real-time updates active
        </div>
      )}

      <div className="posts-container" style={{ padding: 0 }}>
        {posts.length === 0 ? (
          <div
            style={{
              padding: 16,
              background: "#d6daf0",
              border: "1px solid #b7c5d9",
              color: "#707070",
              textAlign: "center",
              fontSize: "9pt",
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
              ogImage={idx === 0 ? ogImage : undefined}
            />
          ))
        )}
        {Array.from(thinkingPosts.values()).map((t) => (
          <div key={`thinking-${t.post_num}`} className="post-item post-reply post-thinking-placeholder">
            <div className="post-header">
              <span className="post-name">{t.username}</span>{" "}
              <span className="post-num">No.{t.post_num}</span>
            </div>
            <div className="post-body">Posting<span className="dot-anim">...</span></div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div style={{ margin: "8px 0", fontSize: "9pt", color: "#707070" }}>
        Total posts: {posts.length}
      </div>

      {/* Bottom navigation */}
      <div className="ochch-nav">
        [<Link href="/">Home</Link>]{" "}
        [<Link href={`/sim/${simId}`}>Simulation</Link>]{" "}
        {thread?.board_id && (
          <>
            [<Link href={`/sim/${simId}/board/${thread.board_id}`}>
              {thread?.board_name}
            </Link>]{" "}
          </>
        )}
        [<a href="#top">Top</a>]
      </div>

      <PersonaModal
        agent={selectedAgent}
        onClose={() => setSelectedAgent(null)}
      />
    </div>
  );
}
