"use client";

import React, { useEffect, useState, use } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import { api, ReportData, Board, PostIndexEntry } from "@/lib/api";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

// ===== Confidence bar =====
function ConfidenceMeter({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color =
    pct >= 70 ? "#155724" : pct >= 40 ? "#856404" : "#721c24";
  return (
    <span className="confidence-meter">
      <span className="confidence-bar">
        <span
          className="confidence-fill"
          style={{ width: `${pct}%`, background: color }}
        />
      </span>
      <strong style={{ color }}>{pct}%</strong>
    </span>
  );
}

// ===== Citation link conversion =====
// [>>N@board-name] → convert to clickable links
function renderWithCitations(
  text: string,
  simId: string,
  boards: Board[],
  postsIndex: Record<string, PostIndexEntry>
): React.ReactElement {
  if (!text) return <></>;

  // Pattern: [>>number@any-string] or [>>number]
  const pattern = /\[>>(\d+)@([^\]]+)\]|\[>>(\d+)\]/g;
  const parts: (string | React.ReactElement)[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    // Append text segment
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }

    const postNum = match[1] || match[3];
    const boardName = match[2] || "";

    // Look up board_id from boards array
    let boardId = "";
    if (boardName) {
      const found = boards.find((b) => b.name === boardName);
      if (found) boardId = found.id;
    }
    // Also look up from posts_index
    if (!boardId && boardName) {
      const key = `${boardName}:${postNum}`;
      const entry = postsIndex[key];
      if (entry) boardId = entry.board_id;
    }

    const href = boardId
      ? `/sim/${simId}/board/${boardId}#post-${postNum}`
      : `/sim/${simId}`;

    parts.push(
      <a
        key={`cite-${match.index}`}
        href={href}
        className="citation-link"
        title={boardName ? `${boardName} >>` + postNum : `>>` + postNum}
      >
        {boardName ? `>>${postNum}@${boardName}` : `>>${postNum}`}
      </a>
    );

    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return (
    <>
      {parts.map((p, i) =>
        typeof p === "string" ? <span key={i}>{p}</span> : p
      )}
    </>
  );
}

// ===== Stance distribution chart =====
const STANCE_COLORS: Record<string, string> = {
  Support: "#4CAF50",
  Oppose: "#F44336",
  Neutral: "#FF9800",
  Skeptical: "#9C27B0",
};
const STANCE_ORDER = ["Support", "Oppose", "Neutral", "Skeptical"];

function StanceDistributionChart({
  distribution,
}: {
  distribution: Record<string, number>;
}) {
  const total = Object.values(distribution).reduce((a, b) => a + b, 0);
  if (total === 0) return null;

  const rows = STANCE_ORDER.filter(
    (s) => distribution[s] !== undefined && distribution[s] > 0
  ).concat(
    Object.keys(distribution).filter(
      (k) => !STANCE_ORDER.includes(k) && distribution[k] > 0
    )
  );

  if (rows.length === 0) return null;

  return (
    <div className="report-section">
      <h2>📊 Stance Distribution</h2>
      <div className="chart-container">
        {rows.map((stance) => {
          const count = distribution[stance] || 0;
          const pct = Math.round((count / total) * 100);
          const color = STANCE_COLORS[stance] || "#607D8B";
          return (
            <div key={stance} className="chart-row">
              <div className="chart-label">{stance}</div>
              <div className="chart-bar-bg">
                <span
                  className="chart-bar-fill"
                  style={{ width: `${pct}%`, background: color }}
                />
              </div>
              <div className="chart-value">
                {count} ({pct}%)
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ===== Discussion activity timeline =====
function ActivityTimeline({ activity }: { activity: number[] }) {
  if (!activity || activity.length === 0) return null;
  const max = Math.max(...activity, 1);

  return (
    <div className="report-section">
      <h2>📈 Discussion Activity</h2>
      <div className="chart-container">
        {activity.map((count, i) => {
          const pct = Math.round((count / max) * 100);
          return (
            <div key={i} className="chart-row">
              <div className="chart-label" style={{ width: 36 }}>
                R{i + 1}
              </div>
              <div className="chart-bar-bg">
                <span
                  className="chart-bar-fill"
                  style={{ width: `${pct}%`, background: "#800000" }}
                />
              </div>
              <div className="chart-value">{count}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ===== Consensus meter =====
function ConsensusMeter({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const dots = 10;
  const filled = Math.round(score * dots);
  const label =
    pct >= 70 ? "High consensus" : pct >= 40 ? "Moderate" : "Low consensus (divisive)";

  return (
    <div className="consensus-meter">
      <span style={{ fontSize: 12, color: "#555", marginRight: 4 }}>
        Consensus:
      </span>
      <span className="consensus-dots">
        {Array.from({ length: dots }).map((_, i) => (
          <span
            key={i}
            className={`consensus-dot ${i < filled ? "filled" : "empty"}`}
          />
        ))}
      </span>
      <strong style={{ fontSize: 12, color: "#800000" }}>
        {pct}% — {label}
      </strong>
    </div>
  );
}

// ===== Text rendering (Markdown + citation links) =====
// Convert [>>N@board-name] to <cite> tags before Markdown parsing
function preprocessCitations(text: string): string {
  return text.replace(
    /\[>>(\d+)@([^\]]+)\]|\[>>(\d+)\]/g,
    (_, num1, board, num2) => {
      const num = num1 || num2;
      const b = board || "";
      return b ? `<cite data-post="${num}" data-board="${b}">>>${num}@${b}</cite>` : `<cite data-post="${num}">>>${num}</cite>`;
    }
  );
}

function TextWithCitations({
  text,
  simId,
  boards,
  postsIndex,
}: {
  text: string;
  simId: string;
  boards: Board[];
  postsIndex: Record<string, PostIndexEntry>;
}) {
  if (!text) return null;

  // Convert [>>N@board-name] to temporary tags
  const preprocessed = preprocessCitations(text);

  return (
    <div className="report-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw]}
        components={{
          // Convert <cite> tags to citation links
          cite: ({ node, ...props }: any) => {
            const postNum = node?.properties?.dataPost;
            const boardName = node?.properties?.dataBoard || "";
            let boardId = "";
            if (boardName) {
              const found = boards.find((b) => b.name === boardName);
              if (found) boardId = found.id;
              if (!boardId) {
                const entry = postsIndex[`${boardName}:${postNum}`];
                if (entry) boardId = entry.board_id;
              }
            }
            const href = boardId
              ? `/sim/${simId}/board/${boardId}#post-${postNum}`
              : `/sim/${simId}`;
            return (
              <a href={href} className="citation-link" title={boardName ? `${boardName} >>${postNum}` : `>>${postNum}`}>
                {boardName ? `>>${postNum}@${boardName}` : `>>${postNum}`}
              </a>
            );
          },
          // Apply styles to tables
          table: ({ children }) => (
            <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 12, margin: "8px 0" }}>
              {children}
            </table>
          ),
          th: ({ children }) => (
            <th style={{ background: "#800000", color: "#fff", padding: "4px 8px", textAlign: "left" }}>
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td style={{ padding: "4px 8px", borderBottom: "1px dotted #ddd" }}>
              {children}
            </td>
          ),
        }}
      >
        {preprocessed}
      </ReactMarkdown>
    </div>
  );
}

// ===== Main page =====
export default function ReportPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id: simId } = use(params);
  const [report, setReport] = useState<ReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        const r = await api.getReport(simId);
        setReport(r);
      } catch (e: any) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [simId]);

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
        ⚠️ Report not yet generated or an error occurred: {error}
        <br />
        <Link href={`/sim/${simId}`}>← Back to Simulation</Link>
      </div>
    );
  }

  const boards = report?.boards ?? [];
  const postsIndex = report?.posts_index ?? {};
  const stanceDist = report?.stance_distribution ?? {};
  const activityByRound = report?.activity_by_round ?? [];
  const consensusScore = report?.consensus_score ?? report?.confidence ?? 0.5;

  return (
    <div>
      <div className="ochch-nav" style={{ marginBottom: 8 }}>
        <Link href="/">TOP</Link>
        <Link href={`/sim/${simId}`}>Simulation</Link>
        <span style={{ color: "#888" }}>▶ Report</span>
      </div>

      {/* Parallel world report badge */}
      <div style={{ marginBottom: 8, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <span
          style={{
            background: "#1a1a2e",
            color: "#7ec8e3",
            border: "1px solid #7ec8e3",
            borderRadius: 4,
            padding: "2px 8px",
            fontSize: 12,
            fontWeight: "bold",
            letterSpacing: "0.05em",
          }}
        >
          🌐 Parallel World Prediction Report
        </span>
        <span style={{ fontSize: 11, color: "#888", fontFamily: "monospace" }}>
          ID: report_{simId.slice(0, 8)}
        </span>
      </div>

      {/* Theme title */}
      {report?.theme && (
        <>
          <div className="report-theme-title">
            🔮 "{report.theme}"
          </div>
          <div className="report-theme-divider">
            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          </div>
        </>
      )}

      <div className="ochch-page-title">📊 Simulation Analysis Report</div>

      <div
        style={{
          fontSize: 12,
          color: "#888",
          marginBottom: 12,
          display: "flex",
          gap: 12,
          alignItems: "center",
          flexWrap: "wrap",
        }}
      >
        <span>
          Confidence: <ConfidenceMeter value={report?.confidence ?? 0} />
        </span>
        <a
          href={`${BASE_URL}/api/simulation/${simId}/report/download?format=md`}
          download
          style={{ color: "#0000ee", fontSize: 12 }}
        >
          📥 Download as Markdown
        </a>
      </div>

      {/* Consensus meter */}
      <div style={{ marginBottom: 12 }}>
        <ConsensusMeter score={consensusScore} />
      </div>

      {/* Stance distribution chart */}
      {Object.keys(stanceDist).length > 0 && (
        <StanceDistributionChart distribution={stanceDist} />
      )}

      {/* Discussion activity timeline */}
      {activityByRound.length > 0 && (
        <ActivityTimeline activity={activityByRound} />
      )}

      {/* Summary */}
      <div className="report-section">
        <h2>🔮 Conclusion / Summary</h2>
        <div className="report-box">
          <TextWithCitations
            text={report?.summary ?? ""}
            simId={simId}
            boards={boards}
            postsIndex={postsIndex}
          />
        </div>
      </div>

      {/* Prediction */}
      {report?.prediction && (
        <div className="report-section">
          <h2>🎯 Predicted Answer</h2>
          <div className="report-box" style={{ background: "#fff8e1" }}>
            <TextWithCitations
              text={report.prediction}
              simId={simId}
              boards={boards}
              postsIndex={postsIndex}
            />
          </div>
        </div>
      )}

      {/* Detailed analysis */}
      <div className="report-section">
        <h2>📝 Detailed Analysis</h2>
        <div className="report-box">
          <TextWithCitations
            text={report?.details ?? ""}
            simId={simId}
            boards={boards}
            postsIndex={postsIndex}
          />
        </div>
      </div>

      {/* Key findings */}
      {report?.key_findings && report.key_findings.length > 0 && (
        <div className="report-section">
          <h2>💡 Key Findings</h2>
          <div className="report-box">
            <ul style={{ margin: 0, paddingLeft: 16 }}>
              {report.key_findings.map((f, i) => (
                <li key={i} style={{ marginBottom: 4 }}>
                  <TextWithCitations
                    text={f}
                    simId={simId}
                    boards={boards}
                    postsIndex={postsIndex}
                  />
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Agent positions */}
      {report?.agent_positions &&
        Object.keys(report.agent_positions).length > 0 && (
          <div className="report-section">
            <h2>👥 Agent Final Positions</h2>
            <table
              style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}
            >
              <thead>
                <tr>
                  <th
                    style={{
                      background: "#800000",
                      color: "#fff",
                      padding: "4px 8px",
                      textAlign: "left",
                      width: 120,
                    }}
                  >
                    Agent
                  </th>
                  <th
                    style={{
                      background: "#800000",
                      color: "#fff",
                      padding: "4px 8px",
                      textAlign: "left",
                    }}
                  >
                    Position
                  </th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(report.agent_positions).map(([name, pos]) => (
                  <tr key={name}>
                    <td
                      style={{
                        padding: "4px 8px",
                        borderBottom: "1px dotted #ddd",
                        fontWeight: "bold",
                        color: "#008000",
                      }}
                    >
                      {name}
                    </td>
                    <td
                      style={{
                        padding: "4px 8px",
                        borderBottom: "1px dotted #ddd",
                      }}
                    >
                      <TextWithCitations
                        text={pos}
                        simId={simId}
                        boards={boards}
                        postsIndex={postsIndex}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

      {/* Turning points */}
      {report?.turning_points && report.turning_points.length > 0 && (
        <div className="report-section">
          <h2>🔄 Discussion Turning Points</h2>
          <div className="report-box">
            <ol style={{ margin: 0, paddingLeft: 16 }}>
              {report.turning_points.map((t, i) => (
                <li key={i} style={{ marginBottom: 4 }}>
                  <TextWithCitations
                    text={t}
                    simId={simId}
                    boards={boards}
                    postsIndex={postsIndex}
                  />
                </li>
              ))}
            </ol>
          </div>
        </div>
      )}

      {/* Consensus building */}
      <div className="report-section">
        <h2>🤝 Consensus Building</h2>
        <div className="report-box">
          <TextWithCitations
            text={report?.consensus ?? ""}
            simId={simId}
            boards={boards}
            postsIndex={postsIndex}
          />
        </div>
      </div>

      {/* Minority views */}
      {report?.minority_views && report.minority_views.length > 0 && (
        <div className="report-section">
          <h2>🌱 Minority Views</h2>
          <div className="report-box">
            <ul style={{ margin: 0, paddingLeft: 16 }}>
              {report.minority_views.map((v, i) => (
                <li key={i} style={{ marginBottom: 4 }}>
                  <TextWithCitations
                    text={v}
                    simId={simId}
                    boards={boards}
                    postsIndex={postsIndex}
                  />
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      <div style={{ marginTop: 16 }}>
        <Link href={`/sim/${simId}/ask`}>
          <button className="ochch-btn" style={{ marginRight: 8 }}>
            ❓ Ask Agents
          </button>
        </Link>
        <Link href={`/sim/${simId}`}>
          <button className="ochch-btn ochch-btn-secondary">
            ← Back to Simulation
          </button>
        </Link>
      </div>
    </div>
  );
}
