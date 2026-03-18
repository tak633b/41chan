"use client";

import { useEffect, useState, use } from "react";
import Link from "next/link";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

interface Answer {
  agent_name: string;
  username: string;
  content: string;
  post_num: number;
  timestamp: string;
}

interface QA {
  question: string;
  answers: Answer[];
  typing?: string | null;
}

export default function AskPage({ params }: { params: Promise<{ id: string }> }) {
  const { id: simId } = use(params);
  const [question, setQuestion] = useState("");
  const [sessions, setSessions] = useState<QA[]>([]);
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);

  // Load question history
  useEffect(() => {
    const loadHistory = async () => {
      try {
        const res = await fetch(
          `${BASE_URL}/api/simulation/${simId}/ask/history`
        );
        if (res.ok) {
          const data = await res.json();
          setHistory(data);
        }
      } catch {}
      setHistoryLoading(false);
    };
    loadHistory();
  }, [simId]);

  const handleAsk = async () => {
    const q = question.trim();
    if (!q || loading) return;

    setQuestion("");
    setLoading(true);

    const sessionIdx = sessions.length;
    setSessions((prev) => [...prev, { question: q, answers: [], typing: null }]);

    try {
      const res = await fetch(`${BASE_URL}/api/simulation/${simId}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q }),
      });

      if (!res.ok) {
        throw new Error(`API error ${res.status}`);
      }

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) return;

      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6));
            if (event.type === "thinking") {
              setSessions((prev) => {
                const next = [...prev];
                next[sessionIdx] = {
                  ...next[sessionIdx],
                  typing: event.data.agent_name,
                };
                return next;
              });
            } else if (event.type === "answer") {
              setSessions((prev) => {
                const next = [...prev];
                next[sessionIdx] = {
                  ...next[sessionIdx],
                  typing: null,
                  answers: [...next[sessionIdx].answers, event.data],
                };
                return next;
              });
            } else if (event.type === "complete") {
              setSessions((prev) => {
                const next = [...prev];
                next[sessionIdx] = {
                  ...next[sessionIdx],
                  typing: null,
                };
                return next;
              });
            }
          } catch {}
        }
      }
    } catch (e: any) {
      setSessions((prev) => {
        const next = [...prev];
        next[sessionIdx] = {
          ...next[sessionIdx],
          typing: null,
          answers: [
            {
              agent_name: "System",
              username: "system",
              content: "Error: " + e.message,
              post_num: 0,
              timestamp: new Date().toLocaleString("en-US"),
            },
          ],
        };
        return next;
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="ochch-nav" style={{ marginBottom: 8 }}>
        <Link href="/">TOP</Link>
        <Link href={`/sim/${simId}`}>Simulation</Link>
        <span style={{ color: "#888" }}>▶ Ask Thread</span>
      </div>

      <div className="ochch-page-title">❓ Ask the Agents</div>

      <div
        style={{
          fontSize: 12,
          color: "#888",
          marginBottom: 10,
          background: "#fff",
          border: "1px solid #ddd",
          padding: "6px 10px",
        }}
      >
        You can ask questions to the agents who participated in the simulation.
        3–5 of the most relevant agents will answer in real time.
      </div>

      {/* Question form */}
      <div className="ask-form">
        <div className="form-group">
          <label style={{ fontWeight: "bold", fontSize: 13 }}>Enter your question</label>
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="e.g. What do you think about AI regulation?"
            rows={3}
            disabled={loading}
            style={{
              width: "100%",
              border: "1px solid #aaa",
              padding: "4px 6px",
              fontFamily: "monospace",
              fontSize: 13,
              marginTop: 4,
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && e.ctrlKey) handleAsk();
            }}
          />
          <div style={{ fontSize: 11, color: "#888", marginTop: 2 }}>
            Ctrl+Enter to submit
          </div>
        </div>
        <button
          className="ochch-btn"
          onClick={handleAsk}
          disabled={loading || !question.trim()}
        >
          {loading ? "Waiting for answers..." : "▶ Ask"}
        </button>
      </div>

      {/* Current session */}
      {sessions.map((session, si) => (
        <div key={si} style={{ marginBottom: 16 }}>
          {/* Question */}
          <div
            style={{
              background: "#ffeeee",
              border: "1px solid #ddd",
              padding: "6px 10px",
              fontWeight: "bold",
              fontSize: 13,
            }}
          >
            [Question] {session.question}
          </div>

          {/* Thinking indicator */}
          {session.typing && (
            <div className="typing-indicator">
              💭 {session.typing} is thinking
              <span className="loading-dots" />
            </div>
          )}

          {/* Answers */}
          <div className="posts-container">
            {session.answers.map((a, ai) => (
              <div key={ai} className="ask-answer">
                <div className="post-header">
                  <span className="post-num">{a.post_num || ai + 1}</span>
                  <span className="post-name">{a.agent_name}</span>
                  <span className="post-time">{a.timestamp}</span>
                  <span className="post-id">
                    ID:<span>{a.username}</span>
                  </span>
                </div>
                <div className="post-body">{a.content}</div>
              </div>
            ))}
          </div>
        </div>
      ))}

      {/* Question history */}
      {!historyLoading && history.length > 0 && (
        <div style={{ marginTop: 20 }}>
          <div
            style={{
              fontWeight: "bold",
              fontSize: 13,
              borderBottom: "1px solid #aaa",
              paddingBottom: 4,
              marginBottom: 8,
            }}
          >
            📜 Past Question History
          </div>
          {history.map((h) => (
            <div key={h.id} style={{ marginBottom: 12 }}>
              <div
                style={{
                  background: "#f0f0f0",
                  border: "1px solid #ddd",
                  padding: "4px 8px",
                  fontSize: 12,
                  fontWeight: "bold",
                }}
              >
                [Question] {h.question}
                <span style={{ color: "#888", fontWeight: "normal", marginLeft: 8 }}>
                  {new Date(h.created_at).toLocaleString("en-US")}
                </span>
              </div>
              {h.answers.map((a: any, ai: number) => (
                <div key={ai} className="ask-answer">
                  <div className="post-header">
                    <span className="post-num">{ai + 1}</span>
                    <span className="post-name">{a.agent_name}</span>
                    <span className="post-time">{a.timestamp}</span>
                    <span className="post-id">
                      ID:<span>{a.username}</span>
                    </span>
                  </div>
                  <div className="post-body">{a.content}</div>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
