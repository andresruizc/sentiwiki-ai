/**
 * Conversation management and persistence utilities
 */

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  stage?: string;
  timestamp: Date;
  route?: "RAG" | "DIRECT";
  documentCount?: number;
  sources?: Array<{ 
    title: string; 
    url?: string; 
    heading?: string; 
    score?: number;
    score_percentage?: number;
    pdf_name?: string;
    headings_with_urls?: Array<{ heading: string; url: string }>;
  }>;
  metadata?: {
    rewrite_attempted?: boolean;
    rewritten_query?: string;
    grade_score?: string;
    [key: string]: any;
  };
}

export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  createdAt: Date;
  updatedAt: Date;
  collection?: string;
}

const STORAGE_KEY = "sentiwiki_conversations";
const MAX_CONVERSATIONS = 50; // Limit to prevent storage issues

/**
 * Load all conversations from localStorage
 */
export function loadConversations(): Conversation[] {
  if (typeof window === "undefined") return [];
  
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return [];
    
    const conversations = JSON.parse(stored) as Conversation[];
    // Convert date strings back to Date objects
    return conversations.map(conv => ({
      ...conv,
      createdAt: new Date(conv.createdAt),
      updatedAt: new Date(conv.updatedAt),
      messages: conv.messages.map(msg => ({
        ...msg,
        timestamp: new Date(msg.timestamp),
      })),
    }));
  } catch (error) {
    console.error("Failed to load conversations:", error);
    return [];
  }
}

/**
 * Save conversations to localStorage
 */
export function saveConversations(conversations: Conversation[]): void {
  if (typeof window === "undefined") return;
  
  try {
    // Limit number of conversations
    const limited = conversations
      .sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime())
      .slice(0, MAX_CONVERSATIONS);
    
    localStorage.setItem(STORAGE_KEY, JSON.stringify(limited));
  } catch (error) {
    console.error("Failed to save conversations:", error);
    // If quota exceeded, try to remove oldest conversations
    if (error instanceof DOMException && error.name === "QuotaExceededError") {
      const reduced = conversations
        .sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime())
        .slice(0, Math.floor(MAX_CONVERSATIONS * 0.7));
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(reduced));
      } catch (e) {
        console.error("Failed to save even after reduction:", e);
      }
    }
  }
}

/**
 * Create a new conversation
 */
export function createConversation(collection?: string): Conversation {
  return {
    id: `conv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    title: "New conversation",
    messages: [],
    createdAt: new Date(),
    updatedAt: new Date(),
    collection,
  };
}

/**
 * Generate a title from the first user message
 */
export function generateConversationTitle(firstMessage: string): string {
  // Take first 50 characters and clean up
  const cleaned = firstMessage.trim().slice(0, 50);
  if (cleaned.length < firstMessage.length) {
    return cleaned + "...";
  }
  return cleaned || "New conversation";
}

/**
 * Update a conversation
 */
export function updateConversation(
  conversations: Conversation[],
  conversationId: string,
  updates: Partial<Conversation>
): Conversation[] {
  return conversations.map(conv => {
    if (conv.id === conversationId) {
      const updated = {
        ...conv,
        ...updates,
        updatedAt: new Date(),
      };
      // Auto-generate title from first message if not set
      if (!updated.title || updated.title === "New conversation") {
        const firstUserMessage = updated.messages.find(m => m.role === "user");
        if (firstUserMessage) {
          updated.title = generateConversationTitle(firstUserMessage.content);
        }
      }
      return updated;
    }
    return conv;
  });
}

/**
 * Delete a conversation
 */
export function deleteConversation(
  conversations: Conversation[],
  conversationId: string
): Conversation[] {
  return conversations.filter(conv => conv.id !== conversationId);
}

/**
 * Export conversation as Markdown
 */
export function exportConversationAsMarkdown(conversation: Conversation): string {
  let markdown = `# ${conversation.title}\n\n`;
  markdown += `**Created:** ${conversation.createdAt.toLocaleString()}\n`;
  markdown += `**Last updated:** ${conversation.updatedAt.toLocaleString()}\n`;
  if (conversation.collection) {
    markdown += `**Collection:** ${conversation.collection}\n`;
  }
  markdown += `\n---\n\n`;
  
  conversation.messages.forEach((message, index) => {
    const role = message.role === "user" ? "User" : "Assistant";
    markdown += `## ${role} (${message.timestamp.toLocaleString()})\n\n`;
    markdown += `${message.content}\n\n`;
    
    if (message.sources && message.sources.length > 0) {
      markdown += `### Sources:\n\n`;
      message.sources.forEach((source, idx) => {
        markdown += `${idx + 1}. ${source.title || source.pdf_name || "Unknown"}`;
        if (source.url) {
          markdown += ` - [View in SentiWiki](${source.url})`;
        }
        if (source.score_percentage !== undefined) {
          markdown += ` (${source.score_percentage}% relevant)`;
        }
        markdown += `\n`;
      });
      markdown += `\n`;
    }
    
    markdown += `---\n\n`;
  });
  
  return markdown;
}

/**
 * Export conversation as JSON
 */
export function exportConversationAsJSON(conversation: Conversation): string {
  return JSON.stringify(conversation, null, 2);
}

/**
 * Download a file
 */
export function downloadFile(content: string, filename: string, mimeType: string): void {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * Calculate conversation statistics
 */
export function getConversationStats(conversation: Conversation) {
  const userMessages = conversation.messages.filter(m => m.role === "user");
  const assistantMessages = conversation.messages.filter(m => m.role === "assistant");
  
  const totalMessages = conversation.messages.length;
  const totalWords = conversation.messages.reduce((acc, msg) => {
    return acc + msg.content.split(/\s+/).filter(word => word.length > 0).length;
  }, 0);
  
  const totalChars = conversation.messages.reduce((acc, msg) => acc + msg.content.length, 0);
  
  // Rough token estimation (1 token ≈ 4 characters for English, but can vary)
  // Using a conservative estimate: tokens ≈ characters / 3.5
  const estimatedTokens = Math.round(totalChars / 3.5);
  
  const totalSources = conversation.messages.reduce((acc, msg) => {
    return acc + (msg.sources?.length || 0);
  }, 0);
  
  const duration = conversation.updatedAt.getTime() - conversation.createdAt.getTime();
  const durationMinutes = Math.round(duration / (1000 * 60));
  
  return {
    totalMessages,
    userMessages: userMessages.length,
    assistantMessages: assistantMessages.length,
    totalWords,
    totalChars,
    estimatedTokens,
    totalSources,
    durationMinutes,
    avgWordsPerMessage: totalMessages > 0 ? Math.round(totalWords / totalMessages) : 0,
  };
}

/**
 * Export conversation as PDF (using browser print API)
 * This creates a printable HTML version that can be saved as PDF
 */
export async function exportConversationAsPDF(conversation: Conversation): Promise<void> {
  // Create a printable HTML document
  let html = `
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8">
      <title>${conversation.title}</title>
      <style>
        body {
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
          line-height: 1.6;
          color: #333;
          max-width: 800px;
          margin: 0 auto;
          padding: 20px;
        }
        h1 {
          color: #1a1a1a;
          border-bottom: 2px solid #e0e0e0;
          padding-bottom: 10px;
          margin-bottom: 20px;
        }
        .metadata {
          background: #f5f5f5;
          padding: 15px;
          border-radius: 5px;
          margin-bottom: 30px;
          font-size: 14px;
        }
        .metadata p {
          margin: 5px 0;
        }
        .message {
          margin-bottom: 30px;
          page-break-inside: avoid;
        }
        .message-header {
          font-weight: bold;
          margin-bottom: 10px;
          color: #555;
          font-size: 14px;
        }
        .user-message {
          background: #e3f2fd;
          padding: 15px;
          border-radius: 8px;
          border-left: 4px solid #2196f3;
        }
        .assistant-message {
          background: #f5f5f5;
          padding: 15px;
          border-radius: 8px;
          border-left: 4px solid #4caf50;
        }
        .message-content {
          white-space: pre-wrap;
          word-wrap: break-word;
        }
        .sources {
          margin-top: 15px;
          padding-top: 15px;
          border-top: 1px solid #ddd;
        }
        .sources-title {
          font-weight: bold;
          margin-bottom: 10px;
          font-size: 14px;
        }
        .source-item {
          margin: 8px 0;
          padding: 8px;
          background: #fff;
          border-radius: 4px;
          font-size: 13px;
        }
        .source-item a {
          color: #2196f3;
          text-decoration: none;
        }
        .timestamp {
          color: #888;
          font-size: 12px;
          margin-top: 5px;
        }
        @media print {
          body {
            padding: 10px;
          }
          .message {
            page-break-inside: avoid;
          }
        }
      </style>
    </head>
    <body>
      <h1>${escapeHtml(conversation.title)}</h1>
      
      <div class="metadata">
        <p><strong>Created:</strong> ${conversation.createdAt.toLocaleString()}</p>
        <p><strong>Last updated:</strong> ${conversation.updatedAt.toLocaleString()}</p>
        ${conversation.collection ? `<p><strong>Collection:</strong> ${escapeHtml(conversation.collection)}</p>` : ''}
        <p><strong>Total messages:</strong> ${conversation.messages.length}</p>
      </div>
  `;
  
  conversation.messages.forEach((message) => {
    const role = message.role === "user" ? "User" : "Assistant";
    const messageClass = message.role === "user" ? "user-message" : "assistant-message";
    
    html += `
      <div class="message">
        <div class="message-header">${role}</div>
        <div class="${messageClass}">
          <div class="message-content">${escapeHtml(message.content)}</div>
          <div class="timestamp">${message.timestamp.toLocaleString()}</div>
        </div>
    `;
    
    if (message.sources && message.sources.length > 0) {
      html += `
        <div class="sources">
          <div class="sources-title">Sources (${message.sources.length}):</div>
      `;
      message.sources.forEach((source, idx) => {
        const sourceName = source.title || source.pdf_name || "Unknown";
        const score = source.score_percentage !== undefined ? ` (${source.score_percentage}% relevant)` : '';
        html += `
          <div class="source-item">
            ${idx + 1}. ${escapeHtml(sourceName)}${score}
            ${source.url ? `<br><a href="${source.url}" target="_blank">${source.url}</a>` : ''}
          </div>
        `;
      });
      html += `</div>`;
    }
    
    html += `</div>`;
  });
  
  html += `
      </body>
    </html>
  `;
  
  // Open print dialog with the HTML content
  const printWindow = window.open('', '_blank');
  if (printWindow) {
    printWindow.document.write(html);
    printWindow.document.close();
    
    // Wait for content to load, then trigger print
    setTimeout(() => {
      printWindow.print();
      // Optionally close after printing
      // printWindow.close();
    }, 250);
  } else {
    // Fallback: create a blob and download
    const blob = new Blob([html], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${conversation.title.replace(/[^a-z0-9]/gi, "_")}.html`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text: string): string {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

