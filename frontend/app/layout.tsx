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
      <head>
        <link
          rel="preconnect"
          href="https://fonts.googleapis.com"
        />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <header className="ochch-header">
          <div className="ochch-site-title">
            <Link href="/">41chan</Link>
          </div>
          <div>
            <Link href="/new">New Simulation</Link>
          </div>
        </header>
        <nav className="ochch-nav">
          [<Link href="/">TOP</Link>]{" "}
          [<Link href="/new">New Sim</Link>]{" "}
          [<span style={{ color: "#222" }}>/sim/ - AI Simulation</span>]
          <span style={{ color: "#888", marginLeft: 8 }}>
            41chan v1.0
          </span>
        </nav>
        <main className="ochch-main">{children}</main>
        <footer
          style={{
            borderTop: "1px solid #b7c5d9",
            padding: "6px 12px",
            fontSize: 11,
            color: "#888",
            marginTop: 20,
            textAlign: "center",
          }}
        >
          All stories are entirely fictional. All trademarks and copyrights belong to their respective owners.
        </footer>
      </body>
    </html>
  );
}
