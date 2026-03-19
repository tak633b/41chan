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
  ogImage?: string;
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

/** Generate a color from poster ID (4chan-style ID coloring) */
function getIdColor(posterId: string): string {
  let hash = 0;
  for (let i = 0; i < posterId.length; i++) {
    hash = ((hash << 5) - hash + posterId.charCodeAt(i)) | 0;
  }
  hash = hash >>> 0;
  const r = (hash & 0xFF0000) >> 16;
  const g = (hash & 0x00FF00) >> 8;
  const b = hash & 0x0000FF;
  // Ensure readable on both light and dark backgrounds
  const lum = 0.299 * r + 0.587 * g + 0.114 * b;
  if (lum > 200) {
    return `rgb(${Math.floor(r * 0.7)}, ${Math.floor(g * 0.7)}, ${Math.floor(b * 0.7)})`;
  }
  return `rgb(${r}, ${g}, ${b})`;
}

export default function PostCard({ post, allPosts, onNameClick, isNew, isFirstPost, threadTitle, ogImage }: Props) {
  const [popupPost, setPopupPost] = useState<PostInfo | null>(null);
  const [popupPos, setPopupPos] = useState({ x: 0, y: 0 });
  // Toggle state for showing real name (default: hidden = anonymous)
  const [showRealName, setShowRealName] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const kotehan = isKotehan(post.agent_name);
  const tripcode = kotehan ? getTripcode(post.agent_name) : null;
  const posterId = getPosterId(post.agent_name);
  const idColor = getIdColor(posterId);

  // Determine display name
  const displayedName = kotehan
    ? post.agent_name
    : showRealName
    ? post.agent_name
    : post.username;

  const nameTitle = kotehan
    ? `View ${post.agent_name}'s profile`
    : showRealName
    ? "Click: view profile / Double-click: return to anonymous"
    : "Click to reveal real name (anonymous mode)";

  const handleNameClick = () => {
    if (kotehan) {
      onNameClick?.(post.agent_name);
    } else if (showRealName) {
      onNameClick?.(post.agent_name);
    } else {
      setShowRealName(true);
    }
  };

  const handleNameDoubleClick = () => {
    if (!kotehan && showRealName) {
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
    const lines = content.split("\n");
    const result: React.ReactNode[] = [];

    lines.forEach((line, lineIdx) => {
      if (line.startsWith(">") && !line.startsWith(">>")) {
        result.push(
          <div
            key={`line-${lineIdx}`}
            style={{ color: "#789922" }}
          >
            {line}
          </div>
        );
      } else {
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

  // OP: transparent+inline, Reply: #d6daf0+display:table
  const isOP = isFirstPost;
  const postClass = `post-item${isOP ? "" : " post-reply"}${isNew ? " post-new" : ""}`;

  return (
    <div className="post-wrapper" ref={containerRef} id={`post-${post.post_num}`}>
    <div
      className={postClass}
    >
      {/* File info for first post */}
      {isFirstPost && ogImage && (
        <div className="post-file-info">
          File: <a href={ogImage} target="_blank" rel="noopener noreferrer" style={{ color: "#34345c" }}>
            {ogImage.split("/").pop()?.slice(0, 40) || "image.jpg"}
          </a>
        </div>
      )}

      {/* OG image for first post */}
      {isFirstPost && ogImage && (
        <div style={{ margin: "4px 0 8px 0" }}>
          <a href={ogImage} target="_blank" rel="noopener noreferrer">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001"}/api/image-proxy?url=${encodeURIComponent(ogImage)}`}
              alt="Article thumbnail"
              style={{
                maxWidth: 250,
                maxHeight: 250,
                border: "1px solid #b7c5d9",
                cursor: "pointer",
              }}
              onError={(e) => {
                (e.target as HTMLImageElement).style.display = "none";
              }}
            />
          </a>
        </div>
      )}

      {/* Post header: Subject Name Timestamp No.N ID:xxx */}
      <div className="post-header">
        {isFirstPost && threadTitle && (
          <span className="post-subject">{threadTitle} </span>
        )}
        <span
          className="post-name"
          style={{ cursor: "pointer" }}
          onClick={handleNameClick}
          onDoubleClick={handleNameDoubleClick}
          title={nameTitle}
        >
          {displayedName}
        </span>
        {kotehan && tripcode && (
          <span className="post-tripcode"> ◆{tripcode}</span>
        )}
        {!kotehan && !showRealName && (
          <span
            style={{
              fontSize: "8pt",
              opacity: 0.4,
              cursor: "pointer",
            }}
            onClick={handleNameClick}
          >
            [?]
          </span>
        )}{" "}
        <span className="post-time">{format4chanTime(post.timestamp)}</span>{" "}
        <span className="post-num">
          No.<a
            href={`#post-${post.post_num}`}
          >
            {post.post_num}
          </a>
        </span>{" "}
        <span className="post-id" style={{ color: idColor }}>
          ID:{posterId}
        </span>
      </div>

      {/* Reply to anchor */}
      {post.reply_to && (
        <div style={{ fontSize: "10pt", marginTop: 2 }}>
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
    </div>
  );
}
