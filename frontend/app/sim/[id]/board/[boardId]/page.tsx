"use client";

import { useEffect, useState, use } from "react";
import Link from "next/link";
import { api, ThreadInfo } from "@/lib/api";

function formatDate(s: string | null) {
  if (!s) return "-";
  try {
    return new Date(s).toLocaleString("en-US", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return s;
  }
}

export default function BoardPage({
  params,
}: {
  params: Promise<{ id: string; boardId: string }>;
}) {
  const { id: simId, boardId } = use(params);
  const [threads, setThreads] = useState<ThreadInfo[]>([]);
  const [boardName, setBoardName] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        const [threadList, boards] = await Promise.all([
          api.getThreads(simId, boardId),
          api.getBoards(simId),
        ]);
        setThreads(threadList);
        const board = boards.find((b) => b.id === boardId);
        setBoardName(board ? `${board.emoji} ${board.name}` : "Board");
      } catch (e: any) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [simId, boardId]);

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
        <span style={{ color: "#888" }}>▶ {boardName}</span>
      </div>

      <div className="ochch-page-title">{boardName} — Threads</div>

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

      {threads.length === 0 ? (
        <div
          style={{
            padding: 16,
            background: "#fff",
            border: "1px solid #ddd",
            color: "#888",
            textAlign: "center",
          }}
        >
          No threads
        </div>
      ) : (
        <table className="thread-list">
          <thead>
            <tr>
              <th style={{ width: 30 }}>#</th>
              <th>Thread Title</th>
              <th style={{ width: 60 }}>Posts</th>
              <th style={{ width: 120 }}>Last Post</th>
            </tr>
          </thead>
          <tbody>
            {threads.map((t, i) => (
              <tr key={t.id}>
                <td style={{ textAlign: "center", color: "#888" }}>{i + 1}</td>
                <td>
                  <Link href={`/sim/${simId}/thread/${t.id}`}>{t.title}</Link>
                </td>
                <td style={{ textAlign: "center" }}>{t.post_count ?? 0}</td>
                <td style={{ fontSize: 11, color: "#888" }}>
                  {formatDate(t.last_post_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
