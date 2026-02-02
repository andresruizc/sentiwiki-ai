import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { readFileSync } from "fs";
import { join } from "path";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "SentiWiki AI",
  description: "AI-powered assistant for querying Copernicus Sentinel Missions documentation (SentiWiki)",
};

/**
 * Read runtime configuration file
 * This file is generated at container startup from environment variables
 */
function getRuntimeConfig() {
  try {
    const configPath = join(process.cwd(), "public", "runtime-config.json");
    const configContent = readFileSync(configPath, "utf-8");
    return JSON.parse(configContent);
  } catch (error) {
    // Config file doesn't exist (e.g., in local dev) - use defaults
    return {
      API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002",
      ENV: process.env.NODE_ENV || "development",
    };
  }
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // Read runtime config on server side
  const runtimeConfig = getRuntimeConfig();
  
  // Inject runtime config into HTML for client-side access
  const configScript = `window.__RUNTIME_CONFIG__ = ${JSON.stringify(runtimeConfig)};`;

  return (
    <html lang="en">
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: configScript,
          }}
        />
      </head>
      <body className={inter.className}>{children}</body>
    </html>
  );
}

