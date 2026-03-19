"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

export default function NewSimulationPage() {
  const router = useRouter();
  const [prompt, setPrompt] = useState("");
  const [scale, setScale] = useState<"auto" | "mini" | "full" | "custom">("auto");
  const [customAgents, setCustomAgents] = useState(8);
  const [customRounds, setCustomRounds] = useState(3);
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [seedUrl, setSeedUrl] = useState("");
  const [seedLoading, setSeedLoading] = useState(false);
  const [seedResult, setSeedResult] = useState<{theme: string; question: string; entities: string[]; background_context: string; og_image?: string; source_url?: string} | null>(null);

  const handleSeedExtract = async () => {
    if (!seedUrl.trim()) {
      setError("Please enter a URL");
      return;
    }
    setSeedLoading(true);
    setError("");
    try {
      const res = await fetch(`${BASE_URL}/api/seed/extract`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: seedUrl }),
      });
      if (!res.ok) throw new Error(`API error ${res.status}`);
      const data = await res.json();
      setSeedResult(data);
      setPrompt(data.question || data.theme || "");
    } catch (e: any) {
      setError("Seed extraction failed: " + e.message);
    } finally {
      setSeedLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) {
      setError("Please enter a question/scenario");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const formData = new FormData();
      formData.append("prompt", prompt);
      formData.append("scale", scale);
      if (scale === "custom") {
        formData.append("custom_agents", String(customAgents));
        formData.append("custom_rounds", String(customRounds));
      }
      if (file) {
        formData.append("seed_file", file);
      }
      if (seedResult) {
        formData.append("seed_data_json", JSON.stringify(seedResult));
      }

      const res = await fetch(`${BASE_URL}/api/simulation/create`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(`API error ${res.status}: ${text}`);
      }

      const data = await res.json();
      router.push(`/sim/${data.simulation_id}`);
    } catch (e: any) {
      setError("Creation failed: " + e.message);
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: "0 20px" }}>
      <div className="ochch-page-title">New Simulation</div>

      <form onSubmit={handleSubmit} className="ochch-form" style={{ margin: "8px 0" }}>
        {error && (
          <div
            style={{
              background: "#eef2ff",
              border: "1px solid #b7c5d9",
              padding: "6px 10px",
              marginBottom: 10,
              color: "#d00000",
              fontSize: "9pt",
            }}
          >
            {error}
          </div>
        )}

        {/* Seed material input */}
        <div className="form-group" style={{ background: "#eef2ff", padding: "10px 12px", border: "1px solid #b7c5d9" }}>
          <label style={{ color: "#af0a0f", fontWeight: "bold" }}>Auto-generate theme from article URL</label>
          <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
            <input
              type="url"
              value={seedUrl}
              onChange={(e) => setSeedUrl(e.target.value)}
              placeholder="https://example.com/news/article..."
              disabled={loading || seedLoading}
              style={{ flex: 1 }}
            />
            <button
              type="button"
              className="ochch-btn"
              onClick={handleSeedExtract}
              disabled={loading || seedLoading || !seedUrl.trim()}
              style={{ whiteSpace: "nowrap", fontSize: "9pt" }}
            >
              {seedLoading ? "Extracting..." : "Extract"}
            </button>
          </div>
          {seedResult && (
            <div style={{ marginTop: 8, fontSize: "9pt", lineHeight: 1.8, background: "#d6daf0", padding: 8, border: "1px solid #b7c5d9" }}>
              <div><strong style={{ color: "#0f0c5d" }}>Theme:</strong> {seedResult.theme}</div>
              <div><strong style={{ color: "#0f0c5d" }}>Issue:</strong> {seedResult.question}</div>
              <div><strong style={{ color: "#0f0c5d" }}>Entities:</strong> {seedResult.entities?.join(", ")}</div>
              {seedResult.og_image && (
                <div style={{ margin: "4px 0" }}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={seedResult.og_image} alt="Article thumbnail" style={{ maxWidth: 200, maxHeight: 150, border: "1px solid #b7c5d9" }} onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
                </div>
              )}
              {seedResult.background_context && (
                <div><strong style={{ color: "#0f0c5d" }}>Background:</strong> {seedResult.background_context.slice(0, 150)}...</div>
              )}
              <div style={{ color: "#34345c", marginTop: 4 }}>Theme auto-filled</div>
            </div>
          )}
        </div>

        <div className="form-group">
          <label>Question / Scenario (required)</label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="e.g. What problems arise in a world where AI has replaced all university lectures?"
            rows={4}
            disabled={loading}
          />
        </div>

        <div className="form-group">
          <label>Seed file (optional: .txt / .md)</label>
          <input
            type="file"
            accept=".txt,.md"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            disabled={loading}
            style={{ border: "none", padding: 0 }}
          />
          <div style={{ fontSize: "9pt", color: "#707070", marginTop: 2 }}>
            Provide detailed background info as a text file
          </div>
        </div>

        <div className="form-group">
          <label>Scale</label>
          <div style={{ display: "flex", gap: 16, marginTop: 4 }}>
            {(["auto", "mini", "full", "custom"] as const).map((s) => (
              <label
                key={s}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 4,
                  cursor: "pointer",
                  fontSize: "10pt",
                }}
              >
                <input
                  type="radio"
                  value={s}
                  checked={scale === s}
                  onChange={() => setScale(s)}
                  disabled={loading}
                />
                {s === "auto"
                  ? "Auto"
                  : s === "mini"
                  ? "Mini (5 agents)"
                  : s === "full"
                  ? "Full (12 agents)"
                  : "Custom"}
              </label>
            ))}
          </div>
        </div>

        {scale === "custom" && (
          <div className="form-group" style={{ display: "flex", gap: 16 }}>
            <div>
              <label>Agent Count</label>
              <input
                type="number"
                value={customAgents}
                min={3}
                max={20}
                onChange={(e) => setCustomAgents(Number(e.target.value))}
                disabled={loading}
                style={{ width: 80 }}
              />
            </div>
            <div>
              <label>Round Count</label>
              <input
                type="number"
                value={customRounds}
                min={1}
                max={100}
                onChange={(e) => setCustomRounds(Number(e.target.value))}
                disabled={loading}
                style={{ width: 80 }}
              />
            </div>
          </div>
        )}

        <button type="submit" className="ochch-btn-primary" disabled={loading}>
          {loading ? "Creating simulation..." : "Start Simulation"}
        </button>
      </form>

      <div
        style={{
          fontSize: "9pt",
          color: "#555",
          background: "#d6daf0",
          border: "1px solid #b7c5d9",
          padding: "8px 10px",
          marginTop: 8,
        }}
      >
        <strong style={{ color: "#0f0c5d" }}>How it works:</strong>
        <ol style={{ margin: "4px 0 0 16px", lineHeight: 1.8 }}>
          <li>Extract entities (people, organizations, concepts) from the seed text</li>
          <li>Auto-generate agents (imageboard participants)</li>
          <li>Auto-generate imageboard boards suited to the theme</li>
          <li>Agents debate in real time</li>
          <li>An analysis report is auto-generated after the simulation completes</li>
        </ol>
      </div>
    </div>
  );
}
