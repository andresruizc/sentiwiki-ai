"use client";

import { useEffect, useState } from "react";
import { healthCheck } from "@/lib/api";
import { CheckCircle2, XCircle, Loader2, AlertCircle } from "lucide-react";

export function ApiStatus() {
  const [status, setStatus] = useState<"checking" | "connected" | "error">("checking");
  const [error, setError] = useState<string>("");
  const [apiUrl, setApiUrl] = useState<string>("");

  useEffect(() => {
    const apiUrlFromEnv = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8002';
    setApiUrl(apiUrlFromEnv);
    
    const testConnection = async () => {
      try {
        const result = await healthCheck();
        setStatus("connected");
        setError("");
      } catch (err) {
        setStatus("error");
        const errorMsg = err instanceof Error ? err.message : "Connection failed";
        setError(errorMsg);
        console.error("API connection test failed:", err);
      }
    };

    testConnection();
    
    // Retry every 5 seconds if failed
    const interval = setInterval(() => {
      if (status === "error") {
        testConnection();
      }
    }, 5000);

    return () => clearInterval(interval);
  }, [status]);

  return (
    <div className="flex items-center gap-2 text-xs">
      {status === "checking" && (
        <>
          <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
          <span className="text-muted-foreground">Checking API...</span>
        </>
      )}
      {status === "connected" && (
        <>
          <CheckCircle2 className="h-3 w-3 text-green-500" />
          <span className="text-green-500">API Connected</span>
        </>
      )}
      {status === "error" && (
        <div className="flex items-center gap-2 text-red-500">
          <XCircle className="h-3 w-3" />
          <span>API Error</span>
          <span 
            className="cursor-help" 
            title={`Cannot connect to ${apiUrl}. Make sure the FastAPI backend is running.`}
          >
            <AlertCircle className="h-3 w-3" />
          </span>
        </div>
      )}
    </div>
  );
}

