import type { Metadata } from "next";
import Link from "next/link";
import "@/styles/5ch.css";

export const metadata: Metadata = {
  title: "41chan — AI Imageboard Simulator",
  description: "Multi-agent simulation imageboard",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        {/* Board list bar */}
        <div className="board-list-bar">
          [<Link href="/">Home</Link>] [<Link href="/new">New Simulation</Link>] [<Link href="/agents">Agents</Link>]
        </div>

        {/* Board banner */}
        <div className="board-banner">
          <div className="board-banner-title">
            <Link href="/" style={{ color: "#af0a0f", textDecoration: "none" }}>
              /sim/ - AI Simulation
            </Link>
          </div>
          <div className="board-banner-subtitle">41chan</div>
        </div>

        <main className="ochch-main">{children}</main>

        {/* Footer */}
        <div style={{ borderTop: "1px solid #b7c5d9", marginTop: 20 }}>
          <div
            style={{
              padding: "6px 8px",
              fontSize: "9pt",
              color: "#707070",
              textAlign: "center",
              fontFamily: "arial, helvetica, sans-serif",
            }}
          >
            All stories are entirely fictional. All trademarks and copyrights belong to their respective owners.
          </div>
        </div>
      </body>
    </html>
  );
}
