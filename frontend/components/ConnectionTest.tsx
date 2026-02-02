"use client";

import { useEffect, useState } from "react";
import { healthCheck } from "@/lib/api";
import { CheckCircle2, XCircle, Loader2 } from "lucide-react";

export function ConnectionTest() {
  const [status, setStatus] = useState<"checking" | "connected" | "error">("checking");
  const [error, setError] = useState<string>("");

  useEffect(() => {
    const testConnection = async () => {
      try {
        const result = await healthCheck();
        setStatus("connected");
        setError("");
      } catch (err) {
        setStatus("error");
        setError(err instanceof Error ? err.message : "Connection failed");
      }
    };

    testConnection();
  }, []);

  return (
    <div className="flex items-center gap-2 text-sm">
      {status === "checking" && (
        <>
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          <span className="text-muted-foreground">Checking connection...</span>
        </>
      )}
      {status === "connected" && (
        <>
          <CheckCircle2 className="h-4 w-4 text-green-500" />
          <span className="text-green-500">Connected to API</span>
        </>
      )}
      {status === "error" && (
        <>
          <XCircle className="h-4 w-4 text-red-500" />
          <span className="text-red-500">API connection failed: {error}</span>
        </>
      )}
    </div>
  );
}

