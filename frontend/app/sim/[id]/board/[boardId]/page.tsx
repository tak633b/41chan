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
      <div style={{ padding: 20, color: "#707070" }}>
        Loading<span className="loading-dots" />
      </div>
    );
  }

  return (
    <div style={{ padding: "0 20px" }}>
      {/* Navigation */}
      <div className="ochch-nav" style={{ marginBottom: 8 }}>
        [<Link href="/">Home</Link>]{" "}
        [<Link href={`/sim/${simId}`}>Simulation</Link>]{" "}
      </div>

      <div className="ochch-page-title">{boardName}</div>
      <div style={{ textAlign: "center", fontSize: "9pt", color: "#707070", marginBottom: 12 }}>
        Threads
      </div>

      {error && (
        <div
          style={{
            background: "#d6daf0",
            border: "1px solid #b7c5d9",
            padding: "6px 10px",
            color: "#d00000",
            fontSize: "9pt",
          }}
        >
          {error}
        </div>
      )}

      {threads.length === 0 ? (
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
                <td style={{ textAlign: "center", color: "#707070" }}>{i + 1}</td>
                <td>
                  <Link href={`/sim/${simId}/thread/${t.id}`}>{t.title}</Link>
                </td>
                <td style={{ textAlign: "center" }}>{t.post_count ?? 0}</td>
                <td style={{ fontSize: "9pt", color: "#707070" }}>
                  {formatDate(t.last_post_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Bottom navigation */}
      <div className="ochch-nav" style={{ marginTop: 12 }}>
        [<Link href="/">Home</Link>]{" "}
        [<Link href={`/sim/${simId}`}>Simulation</Link>]{" "}
        [<a href="#top">Top</a>]
      </div>
    </div>
  );
}
