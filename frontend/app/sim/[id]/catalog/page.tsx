"use client";

import { useEffect, useState, use } from "react";
import Link from "next/link";
import { api, BoardInfo, ThreadInfo } from "@/lib/api";

interface CatalogThread extends ThreadInfo {
  board_name: string;
  first_post_snippet: string;
}

export default function CatalogPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [threads, setThreads] = useState<CatalogThread[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchCatalog() {
      try {
        const boards = await api.getBoards(id);
        const allThreads: CatalogThread[] = [];

        await Promise.all(
          boards.map(async (board: BoardInfo) => {
            try {
              const boardThreads = await api.getThreads(id, board.id);
              const catalogThreads: CatalogThread[] = await Promise.all(
                boardThreads.map(async (t: ThreadInfo) => {
                  let snippet = "";
                  try {
                    const detail = await api.getThread(id, t.id);
                    if (detail.posts.length > 0) {
                      snippet = detail.posts[0].content.slice(0, 50);
                    }
                  } catch {
                    // thread detail fetch failed, use empty snippet
                  }
                  return {
                    ...t,
                    board_name: board.name,
                    first_post_snippet: snippet,
                  };
                })
              );
              allThreads.push(...catalogThreads);
            } catch {
              // board thread fetch failed, skip
            }
          })
        );

        if (!cancelled) {
          // Sort by post count descending (most active first)
          const sorted = [...allThreads].sort(
            (a, b) => b.post_count - a.post_count
          );
          setThreads(sorted);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load catalog");
          setLoading(false);
        }
      }
    }

    fetchCatalog();
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (loading) {
    return (
      <div>
        <div className="catalog-nav">
          [<Link href={`/sim/${id}`}>Return</Link>]
        </div>
        <div style={{ padding: 20, textAlign: "center", color: "#888" }}>
          Loading catalog...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div>
        <div className="catalog-nav">
          [<Link href={`/sim/${id}`}>Return</Link>]
        </div>
        <div style={{ padding: 20, color: "#c00" }}>Error: {error}</div>
      </div>
    );
  }

  return (
    <div>
      <div className="catalog-nav">
        [<Link href={`/sim/${id}`}>Return</Link>]{" "}
        [<a href="#top">Top</a>]
      </div>

      <div className="catalog-title" id="top">
        Catalog
      </div>

      <div className="catalog-grid">
        {threads.map((thread) => (
          <Link
            key={thread.id}
            href={`/sim/${id}/thread/${thread.id}`}
            className="catalog-card"
          >
            <div className="catalog-thumb">
              <div className="catalog-thumb-text">
                {thread.board_name}
              </div>
            </div>
            <div className="catalog-card-info">
              <div className="catalog-card-stats">
                <span>R: {thread.post_count}</span>
              </div>
              <div className="catalog-card-title">{thread.title}</div>
              {thread.first_post_snippet && (
                <div className="catalog-card-snippet">
                  {thread.first_post_snippet}
                  {thread.first_post_snippet.length >= 50 ? "..." : ""}
                </div>
              )}
            </div>
          </Link>
        ))}
      </div>

      {threads.length === 0 && (
        <div style={{ padding: 20, textAlign: "center", color: "#888" }}>
          No threads found.
        </div>
      )}

      <div className="catalog-nav" style={{ marginTop: 12 }}>
        [<Link href={`/sim/${id}`}>Return</Link>]{" "}
        [<a href="#top">Top</a>]
      </div>
    </div>
  );
}
