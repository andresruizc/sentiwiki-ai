/**
 * API client for SentiWiki RAG API
 */

/**
 * Get API URL with runtime config support
 * 
 * Fallback chain:
 * 1. Runtime config (window.__RUNTIME_CONFIG__) - set by layout.tsx from runtime-config.json
 * 2. Build-time env var (process.env.NEXT_PUBLIC_API_URL) - baked in at build time
 * 3. Default: http://localhost:8002 (for local development)
 * 
 * This allows the same Docker image to work with different API URLs via ECS task definition.
 * 
 * IMPORTANT: This function is called each time, not cached, to ensure runtime config is always read.
 */
export function getApiUrl(): string {
  // Client-side: Check for runtime config injected by layout.tsx
  if (typeof window !== 'undefined') {
    const runtimeConfig = (window as any).__RUNTIME_CONFIG__;
    if (runtimeConfig?.API_URL) {
      return runtimeConfig.API_URL;
    }
  }
  
  // Server-side: Try to read from runtime config file
  if (typeof window === 'undefined') {
    try {
      const fs = require('fs');
      const path = require('path');
      const configPath = path.join(process.cwd(), 'public', 'runtime-config.json');
      if (fs.existsSync(configPath)) {
        const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
        if (config.API_URL) {
          return config.API_URL;
        }
      }
    } catch (e) {
      // Ignore errors (file might not exist in dev)
    }
  }
  
  // Fallback to build-time env var or default
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8002';
}

// Export getApiUrl for use throughout the codebase
// All code should call getApiUrl() directly to ensure runtime config is always read

export interface Source {
  title: string;
  url?: string;
  heading?: string;
  score?: number;  // This will be the percentage score
  score_percentage?: number;
  pdf_name?: string;
  headings_with_urls?: Array<{ heading: string; url: string }>;
}

export interface StreamMessage {
  stage: 'routing' | 'routed' | 'retrieving' | 'retrieved' | 'generating' | 'streaming' | 'complete' | 'error';
  message?: string;
  count?: number;
  chunk?: string;
  route?: 'RAG' | 'DIRECT';
  sources?: Source[];
  metadata?: {
    rewrite_attempted?: boolean;
    rewritten_query?: string;
    grade_score?: string;
    [key: string]: any;
  };
}

export interface Collection {
  name: string;
  points_count: number;
  vectors_count: number;
  status: string;
}

export interface CollectionsResponse {
  collections: Collection[];
  total: number;
}

/**
 * Stream chat response using Server-Sent Events (SSE) - Agent-based routing
 */
export async function streamChat(
  query: string,
  options: {
    collection?: string;
    onMessage: (message: StreamMessage) => void;
    onError?: (error: Error) => void;
    onComplete?: () => void;
  }
): Promise<void> {
  const params = new URLSearchParams({
    query,
  });

  if (options.collection) {
    params.append('collection', options.collection);
  }

  const apiUrl = getApiUrl();
  const url = `${apiUrl}/api/v1/chat/stream?${params.toString()}`;

  console.log('🚀 Streaming Chat request (Agent-based)');
  console.log('📍 API URL:', apiUrl);
  console.log('🔗 Full URL:', url);
  console.log('📝 Query:', query);
  console.log('⚙️ Options:', options);

  try {
    console.log('Making fetch request to:', url);
    
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Accept': 'text/event-stream',
        'Cache-Control': 'no-cache',
      },
      // Don't include credentials for CORS
      credentials: 'omit',
    }).catch((fetchError) => {
      console.error('Fetch error details:', {
        message: fetchError.message,
        name: fetchError.name,
        stack: fetchError.stack,
      });
      throw new Error(`Network error: ${fetchError.message}. Make sure the API is running on ${apiUrl}`);
    });

    console.log('Response received:', {
      status: response.status,
      statusText: response.statusText,
      headers: Object.fromEntries(response.headers.entries()),
      ok: response.ok,
    });

    if (!response.ok) {
      let errorText = '';
      try {
        errorText = await response.text();
      } catch (e) {
        errorText = `Status ${response.status}: ${response.statusText}`;
      }
      console.error('Error response:', errorText);
      throw new Error(`HTTP error! status: ${response.status} - ${errorText}`);
    }

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();

    if (!reader) {
      throw new Error('Response body is not readable');
    }

    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();

      if (done) {
        options.onComplete?.();
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const jsonStr = line.slice(6).trim();
            if (!jsonStr) continue; // Skip empty lines
            const data = JSON.parse(jsonStr) as StreamMessage;
            if (data.stage === 'complete') {
              console.log(`📨 SSE [${data.stage}]:`, data);
              console.log(`📚 Sources in complete message:`, data.sources);
            } else if (data.stage === 'streaming') {
              console.log(`📨 SSE [${data.stage}]:`, `chunk: "${data.chunk?.substring(0, 50)}..."`);
            } else {
              console.log(`📨 SSE [${data.stage}]:`, data);
            }
            options.onMessage(data);
          } catch (e) {
            console.error('❌ Failed to parse SSE message:', e, 'Line:', line);
          }
        } else if (line.trim() === '') {
          // Empty line, skip
          continue;
        } else if (line.startsWith('event:') || line.startsWith('id:')) {
          // SSE metadata, skip
          continue;
        }
      }
    }
  } catch (error) {
    console.error('Stream Chat error:', error);
    const errorMessage = error instanceof Error 
      ? error.message 
      : String(error);
    
    // Provide more helpful error messages
    if (errorMessage.includes('Failed to fetch') || errorMessage.includes('NetworkError')) {
      options.onError?.(
        new Error(
          `Cannot connect to API at ${getApiUrl()}. ` +
          `Please ensure:\n` +
          `1. The FastAPI backend is running\n` +
          `2. CORS is configured to allow ${window.location.origin}\n` +
          `3. The API URL is correct: ${getApiUrl()}`
        )
      );
    } else {
      options.onError?.(error instanceof Error ? error : new Error(errorMessage));
    }
  }
}

/**
 * Stream RAG response using Server-Sent Events (SSE) - Legacy endpoint
 * @deprecated Use streamChat instead for agent-based routing
 */
export async function streamRAG(
  query: string,
  options: {
    collection?: string;
    use_reranking?: boolean;
    use_hybrid?: boolean;
    onMessage: (message: StreamMessage) => void;
    onError?: (error: Error) => void;
    onComplete?: () => void;
  }
): Promise<void> {
  const params = new URLSearchParams({
    query,
  });

  if (options.collection) {
    params.append('collection', options.collection);
  }
  if (options.use_reranking !== undefined) {
    params.append('use_reranking', String(options.use_reranking));
  }
  if (options.use_hybrid !== undefined) {
    params.append('use_hybrid', String(options.use_hybrid));
  }

  const apiUrl = getApiUrl();
  const url = `${apiUrl}/api/v1/rag/stream?${params.toString()}`;

  console.log('🚀 Streaming RAG request');
  console.log('📍 API URL:', apiUrl);
  console.log('🔗 Full URL:', url);
  console.log('📝 Query:', query);
  console.log('⚙️ Options:', options);

  try {
    console.log('Making fetch request to:', url);
    
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Accept': 'text/event-stream',
        'Cache-Control': 'no-cache',
      },
      credentials: 'omit',
    }).catch((fetchError) => {
      console.error('Fetch error details:', {
        message: fetchError.message,
        name: fetchError.name,
        stack: fetchError.stack,
      });
      throw new Error(`Network error: ${fetchError.message}. Make sure the API is running on ${apiUrl}`);
    });

    console.log('Response received:', {
      status: response.status,
      statusText: response.statusText,
      headers: Object.fromEntries(response.headers.entries()),
      ok: response.ok,
    });

    if (!response.ok) {
      let errorText = '';
      try {
        errorText = await response.text();
      } catch (e) {
        errorText = `Status ${response.status}: ${response.statusText}`;
      }
      console.error('Error response:', errorText);
      throw new Error(`HTTP error! status: ${response.status} - ${errorText}`);
    }

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();

    if (!reader) {
      throw new Error('Response body is not readable');
    }

    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();

      if (done) {
        options.onComplete?.();
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const jsonStr = line.slice(6).trim();
            if (!jsonStr) continue;
            const data = JSON.parse(jsonStr) as StreamMessage;
            console.log(`📨 SSE [${data.stage}]:`, data.stage === 'streaming' ? `chunk: "${data.chunk?.substring(0, 50)}..."` : data);
            options.onMessage(data);
          } catch (e) {
            console.error('❌ Failed to parse SSE message:', e, 'Line:', line);
          }
        } else if (line.trim() === '') {
          continue;
        } else if (line.startsWith('event:') || line.startsWith('id:')) {
          continue;
        }
      }
    }
  } catch (error) {
    console.error('Stream RAG error:', error);
    const errorMessage = error instanceof Error 
      ? error.message 
      : String(error);
    
    if (errorMessage.includes('Failed to fetch') || errorMessage.includes('NetworkError')) {
      options.onError?.(
        new Error(
          `Cannot connect to API at ${getApiUrl()}. ` +
          `Please ensure:\n` +
          `1. The FastAPI backend is running\n` +
          `2. CORS is configured to allow ${window.location.origin}\n` +
          `3. The API URL is correct: ${getApiUrl()}`
        )
      );
    } else {
      options.onError?.(error instanceof Error ? error : new Error(errorMessage));
    }
  }
}

/**
 * Get list of available collections from the backend API.
 * 
 * Endpoint: GET /api/v1/collections
 * Backend listens on: 0.0.0.0:8002 (server-side)
 * Frontend connects to: localhost:8002 (client-side)
 * 
 * Returns: List of all collections in Qdrant with metadata (name, points_count, etc.)
 */
export async function getCollections(): Promise<CollectionsResponse> {
  const apiUrl = getApiUrl();
  const url = `${apiUrl}/api/v1/collections`;
  console.log('📚 Fetching collections from:', url);
  
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch collections: ${response.statusText}`);
  }
  
  const data = await response.json();
  console.log('✅ Collections loaded:', data.collections?.length || 0, 'collections');
  return data;
}

/**
 * Health check
 */
export async function healthCheck(): Promise<{ status: string }> {
  const apiUrl = getApiUrl();
  const response = await fetch(`${apiUrl}/health`);
  if (!response.ok) {
    throw new Error(`Health check failed: ${response.statusText}`);
  }
  return response.json();
}

