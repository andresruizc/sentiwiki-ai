"use client";

import { cn } from "@/lib/utils";

interface RAGProgressProps {
  stage: string;
  route?: "RAG" | "DIRECT";
  documentCount?: number;
  className?: string;
}

export function RAGProgress({ stage, route, documentCount, className }: RAGProgressProps) {
  let message = "";
  let showDots = true;
  
  switch (stage) {
    case "routing":
      message = "Thinking";
      break;
    case "routed":
      message = route === "RAG" ? "Searching documents" : "Generating answer";
      break;
    case "retrieving":
      message = "Searching documents";
      break;
    case "retrieved":
      message = documentCount 
        ? `Found ${documentCount} document${documentCount === 1 ? "" : "s"}` 
        : "Documents found";
      showDots = false;
      break;
    case "generating":
      message = "Generating answer";
      break;
    case "streaming":
      message = "";
      showDots = false;
      break;
    default:
      return null;
  }

  if (!message && !showDots) {
    return null;
  }

  return (
    <div className={cn("flex items-center gap-1 text-xs text-muted-foreground", className)}>
      <span>{message}</span>
      {showDots && (
        <span className="inline-flex gap-0.5 ml-1">
          <span className="animate-[bounce_1s_ease-in-out_infinite]">.</span>
          <span className="animate-[bounce_1s_ease-in-out_infinite_0.2s]">.</span>
          <span className="animate-[bounce_1s_ease-in-out_infinite_0.4s]">.</span>
        </span>
      )}
    </div>
  );
}

