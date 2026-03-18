"use client";

import { useState, useRef } from "react";
import { PostInfo } from "@/lib/api";

interface Props {
  post: PostInfo;
  allPosts: PostInfo[];
  onNameClick?: (agentName: string) => void;
  isNew?: boolean;
  isFirstPost?: boolean;
  threadTitle?: string;
}

// ─── Name display utility ─────────────────────────────────────────

/** Generate a deterministic numeric hash from a string */
function hashName(name: string): number {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = ((hash << 5) - hash + name.charCodeAt(i)) | 0;
  }
  return hash >>> 0; // unsigned
}

/** Determine if the agent uses a named handle (~20% chance of true) */
function isKotehan(agentName: string): boolean {
  return hashName(agentName) % 10 < 2;
}

/** Generate a tripcode for named handles (◆Abc123 format) */
function getTripcode(agentName: string): string {
  const hash = hashName(agentName);
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz123456789";
  let trip = "";
  let h = hash;
  for (let i = 0; i < 6; i++) {
    trip += chars[h % chars.length];
    h = Math.floor(h / chars.length) + 1;
  }
  return trip;
}

/** Generate a poster ID from the agent name (imageboard-style random ID) */
function getPosterId(agentName: string): string {
  const h = hashName(agentName + "id_salt");
  return h.toString(36).padStart(8, "0").slice(0, 8);
}

export default function PostCard({ post, allPosts, onNameClick, isNew, isFirstPost, threadTitle }: Props) {
  const [popupPost, setPopupPost] = useState<PostInfo | null>(null);
  const [popupPos, setPopupPos] = useState({ x: 0, y: 0 });
  // Toggle state for showing real name (default: hidden = anonymous)
  const [showRealName, setShowRealName] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const kotehan = isKotehan(post.agent_name);
  const tripcode = kotehan ? getTripcode(post.agent_name) : null;
  const posterId = getPosterId(post.agent_name);

  // Determine display name
  const displayedName = kotehan
    ? `${post.agent_name} ◆${tripcode}` // Named handle: always show real name + tripcode
    : showRealName
    ? post.agent_name // Anonymous (real name toggled on)
    : post.username;  // Anonymous (default: Anonymous@board)

  const nameTitle = kotehan
    ? `View ${post.agent_name}'s profile`
    : showRealName
    ? "Click: view profile / Double-click: return to anonymous"
    : "Click to reveal real name (anonymous mode)";

  const nameStyle: React.CSSProperties = {
    cursor: "pointer",
    // Named handle: dark green, anonymous (real name visible): blue, anonymous: maroon
    color: kotehan ? "#006400" : showRealName ? "#0000cc" : "#800000",
    fontWeight: kotehan ? "bold" : "normal",
    userSelect: "none" as const,
  };

  const handleNameClick = () => {
    if (kotehan) {
      // Named handle: click opens profile modal
      onNameClick?.(post.agent_name);
    } else if (showRealName) {
      // Real name visible → open profile modal
      onNameClick?.(post.agent_name);
    } else {
      // Anonymous mode → toggle real name display
      setShowRealName(true);
    }
  };

  const handleNameDoubleClick = () => {
    if (!kotehan && showRealName) {
      // Double-click while real name visible → return to anonymous
      setShowRealName(false);
    }
  };

  const handleAnchorHover = (
    e: React.MouseEvent,
    num: number,
    entering: boolean
  ) => {
    if (!entering) {
      setPopupPost(null);
      return;
    }
    const target = allPosts.find((p) => p.post_num === num);
    if (!target) return;

    const rect = (e.target as HTMLElement).getBoundingClientRect();
    setPopupPost(target);
    setPopupPos({ x: rect.left, y: rect.bottom + 4 });
  };

  // Convert >>N anchors to interactive elements & >>text greentext
  const renderContent = (content: string) => {
    // Split by lines first to handle greentext properly
    const lines = content.split("\n");
    const result: React.ReactNode[] = [];

    lines.forEach((line, lineIdx) => {
      // Check if this line is greentext (starts with >)
      if (line.startsWith(">") && !line.startsWith(">>")) {
        // This is greentext - render it in green
        result.push(
          <div
            key={`line-${lineIdx}`}
            style={{ color: "#789922", fontWeight: "normal" }}
          >
            {line}
          </div>
        );
      } else {
        // Normal line - process for >>N anchors
        const parts = line.split(/(>>\d+)/g);
        const lineContent = parts.map((part, i) => {
          const match = part.match(/^>>(\d+)$/);
          if (match) {
            const num = parseInt(match[1]);
            return (
              <span
                key={i}
                className="anchor-link"
                onMouseEnter={(e) => handleAnchorHover(e, num, true)}
                onMouseLeave={(e) => handleAnchorHover(e, num, false)}
              >
                {part}
              </span>
            );
          }
          return <span key={i}>{part}</span>;
        });

        if (lineIdx > 0) {
          result.push(<br key={`break-${lineIdx}`} />);
        }
        result.push(
          <span key={`line-content-${lineIdx}`}>{lineContent}</span>
        );
      }
    });

    return result;
  };

  // Format timestamp to 4chan style: MM/DD/YY(Day)HH:MM:SS
  const format4chanTime = (ts: string): string => {
    try {
      const d = new Date(ts);
      if (isNaN(d.getTime())) return ts;
      const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
      const mm = String(d.getMonth() + 1).padStart(2, "0");
      const dd = String(d.getDate()).padStart(2, "0");
      const yy = String(d.getFullYear()).slice(-2);
      const day = days[d.getDay()];
      const hh = String(d.getHours()).padStart(2, "0");
      const mi = String(d.getMinutes()).padStart(2, "0");
      const ss = String(d.getSeconds()).padStart(2, "0");
      return `${mm}/${dd}/${yy}(${day})${hh}:${mi}:${ss}`;
    } catch {
      return ts;
    }
  };

  // Deterministic file size/dimensions from post content hash
  const fileHash = hashName(post.post_id || post.content);
  const fileSize = 20 + (fileHash % 180); // 20-200 KB
  const fileWidth = 320 + (fileHash % 960);  // 320-1280
  const fileHeight = 240 + ((fileHash >> 8) % 720); // 240-960

  return (
    <div
      className={`post-item${isNew ? " post-new" : ""}`}
      ref={containerRef}
      id={`post-${post.post_num}`}
    >
      {/* Subject line - only on first post of thread */}
      {isFirstPost && threadTitle && (
        <div className="post-subject">{threadTitle}</div>
      )}

      <div className="post-header">
        <span
          className="post-name"
          style={nameStyle}
          onClick={handleNameClick}
          onDoubleClick={handleNameDoubleClick}
          title={nameTitle}
        >
          {displayedName}
          {!kotehan && !showRealName && (
            <span
              style={{
                fontSize: "0.7em",
                opacity: 0.5,
                marginLeft: 2,
                fontWeight: "normal",
              }}
            >
              [?]
            </span>
          )}
        </span>
        <span className="post-time">{format4chanTime(post.timestamp)}</span>
        <span className="post-id">
          ID:<span>{posterId}</span>
        </span>
        <span className="post-num">
          No.<a
            href={`#post-${post.post_num}`}
            style={{ color: "inherit", textDecoration: "none" }}
          >
            {post.post_num}
          </a>
        </span>
      </div>

      {/* Dummy file info line for first post */}
      {isFirstPost && (
        <div className="post-file-info">
          File: <a href="#" onClick={(e) => e.preventDefault()} style={{ color: "#0066cc", textDecoration: "underline" }}>imageboard_sim.jpg</a>{" "}
          ({fileSize} KB, {fileWidth}x{fileHeight})
        </div>
      )}

      {post.reply_to && (
        <div style={{ fontSize: 12, color: "#666", marginBottom: 2 }}>
          <span
            className="anchor-link"
            onMouseEnter={(e) => handleAnchorHover(e, post.reply_to!, true)}
            onMouseLeave={(e) => handleAnchorHover(e, post.reply_to!, false)}
          >
            &gt;&gt;{post.reply_to}
          </span>
        </div>
      )}

      <div className="post-body">{renderContent(post.content)}</div>

      {popupPost && (
        <div
          className="anchor-popup"
          style={{
            position: "fixed",
            left: Math.min(popupPos.x, window.innerWidth - 420),
            top: popupPos.y,
          }}
        >
          <div style={{ fontWeight: "bold", marginBottom: 2 }}>
            {popupPost.post_num}:{" "}
            {isKotehan(popupPost.agent_name)
              ? `${popupPost.agent_name} ◆${getTripcode(popupPost.agent_name)}`
              : popupPost.username}
          </div>
          <div style={{ whiteSpace: "pre-wrap" }}>
            {popupPost.content.slice(0, 200)}
            {popupPost.content.length > 200 ? "..." : ""}
          </div>
        </div>
      )}
    </div>
  );
}
