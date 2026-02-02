"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import { ToastContainer } from "@/components/ui/toast";
import { useToast } from "@/lib/useToast";
import { streamChat, getCollections, type StreamMessage, type Collection } from "@/lib/api";
import { ArrowUp, Loader2, Plus, Menu, X, Copy, Check, ChevronDown, ChevronUp, RotateCcw } from "lucide-react";
import { ThemeToggle } from "@/components/ThemeToggle";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  type Message,
  type Conversation,
  loadConversations,
  saveConversations,
  createConversation,
  updateConversation,
  deleteConversation,
  exportConversationAsMarkdown,
  exportConversationAsPDF,
  downloadFile,
} from "@/lib/conversations";
import { ConversationList } from "@/components/ConversationList";
import { QuestionSuggestions } from "@/components/QuestionSuggestions";
import { RAGProgress } from "@/components/RAGProgress";

export default function Home() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [selectedCollection, setSelectedCollection] = useState<string>("sentiwiki_index"); // Default collection name
  const [currentStage, setCurrentStage] = useState<string>("");
  const [currentRoute, setCurrentRoute] = useState<"RAG" | "DIRECT" | undefined>(undefined);
  const [currentDocumentCount, setCurrentDocumentCount] = useState<number | undefined>(undefined);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const [expandedSources, setExpandedSources] = useState<Set<string>>(new Set());
  const [sourcesVisible, setSourcesVisible] = useState<Set<string>>(new Set());
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set());
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { toasts, dismissToast, success, error: showError } = useToast();

  // Load conversations and collections on mount
  useEffect(() => {
    // Load saved conversations
    const savedConversations = loadConversations();
    setConversations(savedConversations);
    
    // If there are saved conversations, load the most recent one
    if (savedConversations.length > 0) {
      const mostRecent = savedConversations.sort(
        (a, b) => b.updatedAt.getTime() - a.updatedAt.getTime()
      )[0];
      setCurrentConversationId(mostRecent.id);
      setMessages(mostRecent.messages);
    }

    // Load available collections
    getCollections()
      .then((response) => {
        setCollections(response.collections);
        // If default collection doesn't exist, use the first available one
        if (response.collections.length > 0) {
          const defaultExists = response.collections.some(
            (col) => col.name === selectedCollection
          );
          if (!defaultExists) {
            setSelectedCollection(response.collections[0].name);
          }
        }
      })
      .catch((error) => {
        console.error("Failed to load collections:", error);
      });
  }, []);

  // Auto-save conversation when messages change
  useEffect(() => {
    if (currentConversationId && messages.length > 0) {
      setConversations((prevConversations) => {
        const updated = updateConversation(
          prevConversations,
          currentConversationId,
          { messages }
        );
        saveConversations(updated);
        return updated;
      });
    }
  }, [messages, currentConversationId]);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, currentStage]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [input]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Cmd+K or Ctrl+K: New conversation
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        const newConversation = createConversation(selectedCollection);
        const updated = [newConversation, ...conversations];
        setConversations(updated);
        saveConversations(updated);
        setCurrentConversationId(newConversation.id);
        setMessages([]);
        setInput("");
        setCurrentStage("");
        textareaRef.current?.focus();
      }
      
      // Esc: Close sidebar (if open)
      if (e.key === "Escape" && sidebarOpen) {
        setSidebarOpen(false);
      }
      
      // Cmd+/ or Ctrl+/: Focus textarea
      if ((e.metaKey || e.ctrlKey) && e.key === "/") {
        e.preventDefault();
        textareaRef.current?.focus();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [sidebarOpen, conversations, selectedCollection]);

  // Auto-focus textarea when conversation changes or sidebar closes
  useEffect(() => {
    if (!sidebarOpen && textareaRef.current) {
      // Small delay to ensure DOM is ready
      setTimeout(() => {
        textareaRef.current?.focus();
      }, 100);
    }
  }, [sidebarOpen, currentConversationId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!input.trim() || isLoading) {
      return;
    }

    const queryText = input.trim();
    
    // Create new conversation if none exists
    if (!currentConversationId) {
      const newConversation = createConversation(selectedCollection);
      const updated = [newConversation, ...conversations];
      setConversations(updated);
      saveConversations(updated);
      setCurrentConversationId(newConversation.id);
    }

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: queryText,
      timestamp: new Date(),
    };

    setMessages((prev) => {
      const updated = [...prev, userMessage];
      // Update conversation immediately with user message
      if (currentConversationId) {
        const convUpdated = updateConversation(
          conversations,
          currentConversationId,
          { messages: updated }
        );
        setConversations(convUpdated);
        saveConversations(convUpdated);
      }
      return updated;
    });
    setInput("");
    setIsLoading(true);
    setCurrentStage("");
    setCurrentRoute(undefined);
    setCurrentDocumentCount(undefined);

    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }

    // Create assistant message placeholder
    const assistantMessageId = (Date.now() + 1).toString();
    const assistantMessage: Message = {
      id: assistantMessageId,
      role: "assistant",
      content: "",
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, assistantMessage]);

    // Stream response
    const startTime = Date.now();
    console.log('⏱️ Starting stream at:', new Date().toISOString());
    
    await streamChat(userMessage.content, {
      collection: selectedCollection,
      onMessage: (streamMessage: StreamMessage) => {
        const elapsed = Date.now() - startTime;
        console.log(`⏱️ Message received after ${elapsed}ms - Stage: ${streamMessage.stage}`, streamMessage);
        setCurrentStage(streamMessage.stage);
        if (streamMessage.route) {
          setCurrentRoute(streamMessage.route);
        }
        if (streamMessage.count !== undefined) {
          setCurrentDocumentCount(streamMessage.count);
        }
        
        // Update message stage immediately for all stages
        if (streamMessage.stage === "streaming" && streamMessage.chunk) {
          // For streaming, append content
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessageId
                ? { 
                    ...msg, 
                    content: msg.content + streamMessage.chunk, 
                    stage: "streaming",
                    route: msg.route || streamMessage.route,
                  }
                : msg
            )
          );
        } else {
          // For all other stages, update stage, route, and documentCount
          setMessages((prev) =>
            prev.map((msg) => {
              if (msg.id === assistantMessageId) {
                const updated: Message = {
                  ...msg,
                  stage: streamMessage.stage,
                };
                if (streamMessage.route) {
                  updated.route = streamMessage.route;
                }
                if (streamMessage.count !== undefined) {
                  updated.documentCount = streamMessage.count;
                }
                // Preserve existing route if new one not provided
                if (!updated.route && msg.route) {
                  updated.route = msg.route;
                }
                return updated;
              }
              return msg;
            })
          );
        }
        
        if (streamMessage.stage === "complete") {
          console.log("✅ Complete message received:", streamMessage);
          console.log("📚 Sources in streamMessage:", streamMessage.sources);
          console.log("📊 Metadata in streamMessage:", streamMessage.metadata);
          setMessages((prev) =>
            prev.map((msg) => {
              if (msg.id === assistantMessageId) {
                const updatedMsg: Message = {
                  ...msg,
                  stage: "complete" as const,
                  sources: streamMessage.sources || [],
                  metadata: streamMessage.metadata,
                };
                console.log("📝 Updated message with sources and metadata:", updatedMsg);
                return updatedMsg;
              }
              return msg;
            })
          );
          setIsLoading(false);
          setCurrentStage("");
          setCurrentRoute(undefined);
          setCurrentDocumentCount(undefined);
        } else if (streamMessage.stage === "error") {
          const errorMsg = streamMessage.message || "Unknown error occurred";
          showError(`Error: ${errorMsg}`);
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessageId
                ? {
                    ...msg,
                    content: msg.content || `❌ Error: ${errorMsg}`,
                    stage: "error",
                  }
                : msg
            )
          );
          setIsLoading(false);
          setCurrentStage("");
        }
      },
      onError: (error) => {
        console.error("Stream error:", error);
        const errorMessage = error.message || "Unknown error occurred";
        showError(`Connection error: ${errorMessage}`);
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMessageId
              ? {
                  ...msg,
                  content: msg.content || `❌ Error: ${errorMessage}`,
                  stage: "error",
                }
              : msg
          )
        );
        setIsLoading(false);
        setCurrentStage("");
        setCurrentRoute(undefined);
        setCurrentDocumentCount(undefined);
      },
      onComplete: () => {
        setIsLoading(false);
        setCurrentStage("");
        setCurrentRoute(undefined);
        setCurrentDocumentCount(undefined);
      },
    });
  };

  const handleNewChat = useCallback(() => {
    const newConversation = createConversation(selectedCollection);
    const updated = [newConversation, ...conversations];
    setConversations(updated);
    saveConversations(updated);
    setCurrentConversationId(newConversation.id);
    setMessages([]);
    setInput("");
    setCurrentStage("");
  }, [conversations, selectedCollection]);

  const handleSelectConversation = useCallback((conversationId: string) => {
    const conversation = conversations.find((c) => c.id === conversationId);
    if (conversation) {
      setCurrentConversationId(conversationId);
      setMessages(conversation.messages);
      setInput("");
      setCurrentStage("");
    }
  }, [conversations]);

  const handleDeleteConversation = useCallback((conversationId: string) => {
    const updated = deleteConversation(conversations, conversationId);
    setConversations(updated);
    saveConversations(updated);
    
    if (conversationId === currentConversationId) {
      if (updated.length > 0) {
        // Load the most recent conversation
        const mostRecent = updated.sort(
          (a, b) => b.updatedAt.getTime() - a.updatedAt.getTime()
        )[0];
        setCurrentConversationId(mostRecent.id);
        setMessages(mostRecent.messages);
      } else {
        // No conversations left, create a new one
        handleNewChat();
      }
    }
  }, [conversations, currentConversationId, handleNewChat]);

  const handleRenameConversation = useCallback((conversationId: string, newTitle: string) => {
    const updated = updateConversation(conversations, conversationId, { title: newTitle });
    setConversations(updated);
    saveConversations(updated);
  }, [conversations]);

  const handleExportConversation = useCallback((conversation: Conversation, format: "markdown" | "pdf") => {
    if (format === "markdown") {
      const markdown = exportConversationAsMarkdown(conversation);
      const filename = `${conversation.title.replace(/[^a-z0-9]/gi, "_")}.md`;
      downloadFile(markdown, filename, "text/markdown");
    } else if (format === "pdf") {
      exportConversationAsPDF(conversation);
    }
  }, []);

  const handleCopyMessage = async (content: string, messageId: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedMessageId(messageId);
      setTimeout(() => {
        setCopiedMessageId(null);
      }, 2000);
    } catch (err) {
      console.error("Failed to copy text:", err);
      showError("Failed to copy message");
    }
  };

  const handleRegenerateResponse = useCallback(async () => {
    if (messages.length === 0 || isLoading) return;
    
    // Find the last user message
    const lastUserMessage = [...messages].reverse().find((msg) => msg.role === "user");
    if (!lastUserMessage) return;

    // Remove the last assistant message(s) until we find a user message
    const lastUserIndex = messages.findIndex((msg) => msg.id === lastUserMessage.id);
    const messagesToKeep = messages.slice(0, lastUserIndex + 1);
    setMessages(messagesToKeep);

    // Update conversation
    if (currentConversationId) {
      const convUpdated = updateConversation(
        conversations,
        currentConversationId,
        { messages: messagesToKeep }
      );
      setConversations(convUpdated);
      saveConversations(convUpdated);
    }

    // Resubmit the query
    setIsLoading(true);
    setCurrentStage("");
    setCurrentRoute(undefined);
    setCurrentDocumentCount(undefined);

    const assistantMessageId = (Date.now() + 1).toString();
    const assistantMessage: Message = {
      id: assistantMessageId,
      role: "assistant",
      content: "",
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, assistantMessage]);

    await streamChat(lastUserMessage.content, {
      collection: selectedCollection,
      onMessage: (streamMessage: StreamMessage) => {
        setCurrentStage(streamMessage.stage);
        if (streamMessage.route) {
          setCurrentRoute(streamMessage.route);
        }
        if (streamMessage.count !== undefined) {
          setCurrentDocumentCount(streamMessage.count);
        }
        
        if (streamMessage.stage === "streaming" && streamMessage.chunk) {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessageId
                ? { 
                    ...msg, 
                    content: msg.content + streamMessage.chunk, 
                    stage: "streaming",
                    route: msg.route || streamMessage.route,
                  }
                : msg
            )
          );
        } else {
          setMessages((prev) =>
            prev.map((msg) => {
              if (msg.id === assistantMessageId) {
                const updated: Message = {
                  ...msg,
                  stage: streamMessage.stage,
                };
                if (streamMessage.route) {
                  updated.route = streamMessage.route;
                }
                if (streamMessage.count !== undefined) {
                  updated.documentCount = streamMessage.count;
                }
                if (!updated.route && msg.route) {
                  updated.route = msg.route;
                }
                return updated;
              }
              return msg;
            })
          );
        }
        
        if (streamMessage.stage === "complete") {
          setMessages((prev) =>
            prev.map((msg) => {
              if (msg.id === assistantMessageId) {
                return {
                  ...msg,
                  stage: "complete" as const,
                  sources: streamMessage.sources || [],
                  metadata: streamMessage.metadata,
                };
              }
              return msg;
            })
          );
          setIsLoading(false);
          setCurrentStage("");
          setCurrentRoute(undefined);
          setCurrentDocumentCount(undefined);
        } else if (streamMessage.stage === "error") {
          const errorMsg = streamMessage.message || "Unknown error occurred";
          showError(`Error: ${errorMsg}`);
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessageId
                ? {
                    ...msg,
                    content: msg.content || `❌ Error: ${errorMsg}`,
                    stage: "error",
                  }
                : msg
            )
          );
          setIsLoading(false);
          setCurrentStage("");
        }
      },
      onError: (error) => {
        const errorMessage = error.message || "Unknown error occurred";
        showError(`Connection error: ${errorMessage}`);
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMessageId
              ? {
                  ...msg,
                  content: msg.content || `❌ Error: ${errorMessage}`,
                  stage: "error",
                }
              : msg
          )
        );
        setIsLoading(false);
        setCurrentStage("");
        setCurrentRoute(undefined);
        setCurrentDocumentCount(undefined);
      },
      onComplete: () => {
        setIsLoading(false);
        setCurrentStage("");
        setCurrentRoute(undefined);
        setCurrentDocumentCount(undefined);
      },
    });
  }, [messages, isLoading, currentConversationId, conversations, selectedCollection, showError]);

  const toggleSourcesExpansion = (messageId: string) => {
    setExpandedSources((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(messageId)) {
        newSet.delete(messageId);
      } else {
        newSet.add(messageId);
      }
      return newSet;
    });
  };

  const toggleSourcesVisibility = (messageId: string) => {
    setSourcesVisible((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(messageId)) {
        newSet.delete(messageId);
      } else {
        newSet.add(messageId);
      }
      return newSet;
    });
  };

  const toggleSectionExpansion = (sourceKey: string) => {
    setExpandedSections((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(sourceKey)) {
        newSet.delete(sourceKey);
      } else {
        newSet.add(sourceKey);
      }
      return newSet;
    });
  };

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar - Estilo ChatGPT */}
      <aside
        className={`${
          sidebarOpen ? "w-64" : "w-0"
        } transition-all duration-300 bg-gradient-to-b from-card/95 to-card/90 backdrop-blur-md flex flex-col overflow-hidden border-r border-border/50 shadow-xl`}
      >
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Header del Sidebar */}
          <div className="p-4">
            <Button
              onClick={handleNewChat}
              className="w-full justify-center bg-gradient-to-r from-primary to-primary/90 text-primary-foreground hover:from-primary hover:to-primary rounded-xl shadow-md text-sm transition-all duration-300 hover:scale-105"
            >
              <Plus className="h-4 w-4 mr-2" />
              New conversation
            </Button>
          </div>

          {/* Historial de conversaciones */}
          <div className="flex-1 overflow-y-auto scrollbar-thin p-2">
            <div className="mb-2 px-2">
              <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Conversations
              </h3>
            </div>
            <ConversationList
              conversations={conversations}
              currentConversationId={currentConversationId}
              onSelectConversation={handleSelectConversation}
              onDeleteConversation={handleDeleteConversation}
              onRenameConversation={handleRenameConversation}
              onExportConversation={handleExportConversation}
            />
          </div>
        </div>
        
        {/* Selector de colección en la parte inferior */}
        {collections.length > 0 && (
          <div className="p-3 border-t border-border/30">
            <div className="relative" title={selectedCollection}>
              <label className="text-xs font-medium text-muted-foreground mb-1.5 block">
                Collection
              </label>
              <Select
                value={selectedCollection}
                onChange={(e) => setSelectedCollection(e.target.value)}
                className="h-8 text-xs w-full border-border/40 bg-background/40 hover:bg-background/60 hover:border-border/60 transition-all text-muted-foreground focus:text-foreground focus-visible:ring-1 focus-visible:ring-ring/50 pr-7"
              >
                {collections.map((collection) => (
                  <option key={collection.name} value={collection.name}>
                    {collection.name}
                  </option>
                ))}
              </Select>
            </div>
          </div>
        )}
      </aside>

      {/* Área principal de chat */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header superior con botón de menú */}
        <header className="h-14 flex items-center justify-between px-4 bg-gradient-to-r from-card/90 via-card/80 to-card/90 backdrop-blur-md border-b border-border/30 shadow-sm">
          <div className="flex items-center">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="mr-2 hover:bg-primary/10 transition-all duration-200"
            >
              {sidebarOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </Button>
            {!sidebarOpen && (
              <div className="flex items-center gap-2 animate-[fadeInUp_0.3s_ease-out]">
                <div className="w-6 h-6 rounded bg-gradient-to-br from-primary via-primary to-blue-500 flex items-center justify-center shadow-sm">
                  <span className="text-primary-foreground text-xs font-bold">S</span>
                </div>
                <h1 className="text-lg font-semibold bg-gradient-to-r from-foreground to-primary bg-clip-text text-transparent">
                  SentiWiki AI
                </h1>
              </div>
            )}
          </div>
          <ThemeToggle />
        </header>

        {/* Área de mensajes */}
        <div className="flex-1 overflow-y-auto scrollbar-thin">
          <div className="container mx-auto px-4 py-8 max-w-3xl">
            {messages.length === 0 && (
              <div className="flex flex-col items-center justify-center min-h-[60vh] animate-[fadeInUp_0.6s_ease-out]">
                <div className="mb-6 text-center">
                  <div className="relative w-16 h-16 rounded-2xl bg-gradient-to-br from-primary via-primary to-blue-500 flex items-center justify-center mx-auto shadow-lg mb-4 animate-[float_6s_ease-in-out_infinite]">
                    <span className="text-primary-foreground text-2xl font-bold">S</span>
                  </div>
                  <h2 className="text-3xl font-bold mb-3 text-foreground bg-gradient-to-r from-foreground via-primary to-foreground bg-clip-text">
                    SentiWiki AI
                  </h2>
                  <p className="text-muted-foreground mb-2 max-w-md text-base mx-auto leading-relaxed">
                    Ask questions about Sentinel missions from the Copernicus program
                  </p>
                  <p className="text-xs text-muted-foreground/70 max-w-md mx-auto">
                    Powered by SentiWiki Documentation
                  </p>
                </div>
                <div className="w-full max-w-2xl mt-8">
                  <QuestionSuggestions
                    onSelectQuestion={(question) => {
                      setInput(question);
                      textareaRef.current?.focus();
                    }}
                  />
                </div>
              </div>
            )}

            <div className="space-y-6">
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={`flex gap-4 ${
                    message.role === "user" ? "justify-end" : "justify-start"
                  }`}
                >
                  {message.role === "assistant" && (
                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-primary via-primary to-blue-500 flex items-center justify-center shrink-0 shadow-md">
                      <span className="text-primary-foreground text-xs font-bold">S</span>
                    </div>
                  )}
                  <div className="flex flex-col max-w-[92%] md:max-w-[88%] lg:max-w-[85%]">
                    <div
                      className={`rounded-2xl px-4 py-3 transition-all duration-300 ${
                        message.role === "user"
                          ? "bg-gradient-to-br from-primary to-primary/90 text-primary-foreground shadow-md"
                          : "bg-gradient-to-br from-card to-card/80 text-foreground border border-border/50 shadow-md hover:shadow-lg backdrop-blur-sm"
                      }`}
                    >
                      {message.content ? (
                        message.role === "assistant" ? (
                          <div className="prose prose-sm dark:prose-invert max-w-none break-words">
                            <ReactMarkdown
                              remarkPlugins={[remarkGfm]}
                              components={{
                                p: ({ children }) => (
                                  <p className="mb-2 last:mb-0">{children}</p>
                                ),
                                h1: ({ children }) => (
                                  <h1 className="text-xl font-bold mb-2 mt-4 first:mt-0">{children}</h1>
                                ),
                                h2: ({ children }) => (
                                  <h2 className="text-lg font-semibold mb-2 mt-3 first:mt-0">{children}</h2>
                                ),
                                h3: ({ children }) => (
                                  <h3 className="text-base font-semibold mb-2 mt-2 first:mt-0">{children}</h3>
                                ),
                                ul: ({ children }) => (
                                  <ul className="list-disc list-outside mb-2 space-y-1 ml-4 pl-0">{children}</ul>
                                ),
                                ol: ({ children }) => (
                                  <ol className="list-decimal list-outside mb-2 space-y-1 ml-4 pl-0">{children}</ol>
                                ),
                                li: ({ children }) => (
                                  <li className="pl-2 leading-relaxed">{children}</li>
                                ),
                                code: ({ children, className, ...props }) => {
                                  const match = /language-(\w+)/.exec(className || '');
                                  const isInline = !match && !className?.includes('language-');
                                  return isInline ? (
                                    <code className="bg-muted-foreground/20 px-1 py-0.5 rounded text-xs font-mono" {...props}>
                                      {children}
                                    </code>
                                  ) : (
                                    <code className={className} {...props}>
                                      {children}
                                    </code>
                                  );
                                },
                                pre: ({ children, ...props }) => {
                                  return (
                                    <pre className="bg-muted-foreground/20 p-2 rounded text-xs font-mono overflow-x-auto mb-2" {...props}>
                                      {children}
                                    </pre>
                                  );
                                },
                                blockquote: ({ children }) => (
                                  <blockquote className="border-l-4 border-foreground/30 pl-4 italic my-2">
                                    {children}
                                  </blockquote>
                                ),
                                strong: ({ children }) => (
                                  <strong className="font-semibold">{children}</strong>
                                ),
                                em: ({ children }) => (
                                  <em className="italic">{children}</em>
                                ),
                                a: ({ href, children }) => (
                                  <a
                                    href={href}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-primary hover:text-primary/80 hover:underline transition-colors"
                                  >
                                    {children}
                                  </a>
                                ),
                              }}
                            >
                              {message.content}
                            </ReactMarkdown>
                            {message.stage === "streaming" && (
                              <span className="inline-block w-2 h-4 bg-current animate-pulse ml-1" />
                            )}
                            {/* Sources section - show below answer (3 by default, expandable to all) */}
                            {/* Hide sources if documents were not relevant (grade_score === "no") */}
                            {(() => {
                              // Don't show sources if documents were not relevant
                              if (message.metadata?.grade_score === "no") {
                                return null;
                              }
                              
                              console.log("🔍 Checking sources for message:", message.id, "Sources:", message.sources);
                              // Filter sources with score >= 50%
                              const allSources = (message.sources || []).filter((source) => {
                                const scorePercentage = source.score_percentage ?? (source.score ? Math.round(source.score * 100 * 10) / 10 : 0);
                                return scorePercentage >= 50;
                              });
                              const isSourcesVisible = sourcesVisible.has(message.id);
                              const isExpanded = expandedSources.has(message.id);
                              const defaultSourcesCount = 3;
                              const visibleSources = isExpanded 
                                ? allSources
                                : allSources.slice(0, defaultSourcesCount);
                              const hasMoreSources = allSources.length > defaultSourcesCount;
                              
                              return allSources.length > 0 ? (
                                <div className="mt-5 pt-4 border-t border-border/30">
                                  <div className="flex items-center justify-between mb-3">
                                    <div className="flex items-center gap-2">
                                      
                                      <span className="text-xs font-semibold text-foreground">
                                        Sources ({allSources.length})
                                      </span>
                                    </div>
                                    <Button
                                      variant="ghost"
                                      size="sm"
                                      onClick={() => toggleSourcesVisibility(message.id)}
                                      className="h-7 px-2.5 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/50"
                                    >
                                      {isSourcesVisible ? (
                                        <>
                                          <ChevronUp className="h-3 w-3 mr-1" />
                                          Hide
                                        </>
                                      ) : (
                                        <>
                                          <ChevronDown className="h-3 w-3 mr-1" />
                                          Show
                                        </>
                                      )}
                                    </Button>
                                  </div>
                                  {isSourcesVisible && (
                                    <>
                                      <div className="flex flex-col gap-2">
                                        {visibleSources.map((source, idx) => {
                                          // Use pdf_name if available, otherwise fallback to title
                                          let pdfName = source.pdf_name || source.title || "Unknown";
                                          // Remove .md extension if present
                                          if (pdfName.endsWith(".md")) {
                                            pdfName = pdfName.slice(0, -3);
                                          }
                                          // Use score_percentage if available, otherwise calculate from score
                                          const scorePercentage = source.score_percentage ?? (source.score ? Math.round(source.score * 100 * 10) / 10 : 0);
                                          const hasUrl = source.url && source.url.trim() !== "";
                                          
                                          // Use headings_with_urls from backend
                                          const sectionsWithUrls = source.headings_with_urls || [];
                                          
                                          // Create unique key for this source
                                          const sourceKey = `${message.id}-${idx}`;
                                          const areSectionsExpanded = expandedSections.has(sourceKey);
                                          
                                          const maxVisibleSections = 3;
                                          const visibleSections = areSectionsExpanded
                                            ? sectionsWithUrls
                                            : sectionsWithUrls.slice(0, maxVisibleSections);
                                          const hiddenSectionsCount = sectionsWithUrls.length - maxVisibleSections;
                                          
                                          return (
                                            <div
                                              key={idx}
                                              className="group relative bg-gradient-to-br from-card/80 to-card/60 hover:from-card hover:to-card/90 border border-border/40 hover:border-primary/40 rounded-xl p-3 transition-all duration-300 hover:shadow-lg hover:-translate-y-0.5 backdrop-blur-sm"
                                            >
                                              <div className="flex items-start justify-between gap-3">
                                                <div className="flex-1 min-w-0">
                                                  <div className="flex items-center gap-2 mb-2">
                                                    {hasUrl ? (
                                                      <a
                                                        href={source.url}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="font-semibold text-sm text-foreground hover:text-primary transition-colors truncate"
                                                        title={`View in SentiWiki: ${source.url}`}
                                                      >
                                                        {pdfName}
                                                      </a>
                                                    ) : (
                                                      <span className="font-semibold text-sm text-foreground">{pdfName}</span>
                                                    )}
                                                    <span className="text-xs font-medium text-muted-foreground">
                                                      {scorePercentage}%
                                                    </span>
                                                  </div>
                                                  {sectionsWithUrls.length > 0 && (
                                                    <div className="mt-2.5 pt-2.5 border-t border-border/20">
                                                      <div className="flex flex-wrap gap-1.5">
                                                        {visibleSections.map((section, sectionIdx) => {
                                                          const displayHeading = section.heading.split(" > ").pop() || section.heading;
                                                          return (
                                                            <a
                                                              key={sectionIdx}
                                                              href={section.url}
                                                              target="_blank"
                                                              rel="noopener noreferrer"
                                                              className="inline-flex items-center px-2.5 py-1 text-[10px] font-medium bg-gradient-to-r from-primary/8 to-primary/5 hover:from-primary/15 hover:to-primary/10 text-primary hover:text-primary/90 rounded-lg transition-all duration-200 border border-primary/15 hover:border-primary/30 hover:shadow-sm hover:-translate-y-0.5"
                                                              title={`View section: ${section.heading}`}
                                                            >
                                                              {displayHeading}
                                                            </a>
                                                          );
                                                        })}
                                                        {hiddenSectionsCount > 0 && !areSectionsExpanded && (
                                                          <button
                                                            onClick={() => toggleSectionExpansion(sourceKey)}
                                                            className="inline-flex items-center px-2 py-1 text-[10px] font-medium bg-muted/50 hover:bg-muted text-muted-foreground hover:text-foreground rounded-md transition-colors border border-border/30 hover:border-border/50 cursor-pointer"
                                                          >
                                                            +{hiddenSectionsCount} more
                                                          </button>
                                                        )}
                                                        {areSectionsExpanded && sectionsWithUrls.length > maxVisibleSections && (
                                                          <button
                                                            onClick={() => toggleSectionExpansion(sourceKey)}
                                                            className="inline-flex items-center px-2 py-1 text-[10px] font-medium bg-muted/50 hover:bg-muted text-muted-foreground hover:text-foreground rounded-md transition-colors border border-border/30 hover:border-border/50 cursor-pointer"
                                                          >
                                                            Show less
                                                          </button>
                                                        )}
                                                      </div>
                                                    </div>
                                                  )}
                                                </div>
                                              </div>
                                            </div>
                                          );
                                        })}
                                      </div>
                                      {hasMoreSources && (
                                        <div className="mt-3 pt-2 border-t border-border/20">
                                          <Button
                                            variant="ghost"
                                            size="sm"
                                            onClick={() => toggleSourcesExpansion(message.id)}
                                            className="h-7 px-3 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/50 w-full"
                                          >
                                            {isExpanded ? (
                                              <>
                                                <ChevronUp className="h-3 w-3 mr-1.5" />
                                                Show less
                                              </>
                                            ) : (
                                              <>
                                                <ChevronDown className="h-3 w-3 mr-1.5" />
                                                View all sources ({allSources.length})
                                              </>
                                            )}
                                          </Button>
                                        </div>
                                      )}
                                    </>
                                  )}
                                </div>
                              ) : null;
                            })()}
                          </div>
                        ) : (
                          <div className="whitespace-pre-wrap break-words text-sm leading-relaxed">
                            {message.content}
                          </div>
                        )
                      ) : (
                        <RAGProgress
                          stage={message.stage || currentStage || "routing"}
                          route={message.route || currentRoute}
                          documentCount={message.documentCount || currentDocumentCount}
                        />
                      )}
                    </div>
                    {message.role === "assistant" && message.content && (
                      <div className="flex justify-start mt-1 gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleCopyMessage(message.content, message.id)}
                          className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground hover:bg-primary/5 transition-all duration-200"
                        >
                          {copiedMessageId === message.id ? (
                            <>
                              <Check className="h-3 w-3 mr-1 text-green-500" />
                              <span className="text-green-500">Copied</span>
                            </>
                          ) : (
                            <>
                              <Copy className="h-3 w-3 mr-1" />
                              Copy
                            </>
                          )}
                        </Button>
                        {message.stage === "complete" && !isLoading && messages[messages.length - 1]?.id === message.id && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={handleRegenerateResponse}
                            className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground hover:bg-primary/5 transition-all duration-200"
                            title="Regenerate response"
                          >
                            <RotateCcw className="h-3 w-3 mr-1" />
                            Regenerate
                          </Button>
                        )}
                      </div>
                    )}
                  </div>
                  {message.role === "user" && (
                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-muted to-muted/80 flex items-center justify-center shrink-0 shadow-md">
                      <span className="text-foreground text-sm font-semibold">Tú</span>
                    </div>
                  )}
                </div>
              ))}
              {currentStage && !messages.some((m) => m.stage === currentStage) && (
                <div className="flex justify-start gap-4">
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-primary via-primary to-blue-500 flex items-center justify-center shrink-0 shadow-md">
                    <span className="text-primary-foreground text-xs font-bold">S</span>
                  </div>
                  <div className="bg-gradient-to-br from-card to-card/80 rounded-2xl px-4 py-3 border border-border/50 shadow-md backdrop-blur-sm">
                    <RAGProgress
                      stage={currentStage}
                      route={currentRoute}
                      documentCount={currentDocumentCount}
                    />
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          </div>
        </div>

        {/* Input Area - Estilo ChatGPT */}
        <div className="bg-gradient-to-t from-background via-background to-background/80">
          <div className="container mx-auto px-4 py-4 max-w-3xl">
            <form onSubmit={handleSubmit} className="relative">
              <div className="relative flex items-end gap-2 bg-gradient-to-br from-card to-card/90 border border-border/50 rounded-2xl shadow-lg p-3 backdrop-blur-md transition-all duration-300 hover:shadow-xl hover:border-border/70">
                <Textarea
                  ref={textareaRef}
                  value={input}
                  onChange={(e) => {
                    setInput(e.target.value);
                  }}
                  placeholder="Ask your question about Sentinel missions..."
                  disabled={isLoading}
                  className="min-h-[52px] max-h-[200px] resize-none border-0 bg-transparent focus-visible:ring-0 focus-visible:ring-offset-0 shadow-none text-sm pr-12"
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      handleSubmit(e);
                    }
                  }}
                  rows={1}
                />
                <Button
                  type="submit"
                  disabled={isLoading || !input.trim()}
                  size="icon"
                  className="h-8 w-8 rounded-xl bg-gradient-to-br from-primary to-primary/90 text-primary-foreground hover:from-primary hover:to-primary disabled:opacity-50 disabled:cursor-not-allowed shrink-0 mb-1 shadow-md transition-all duration-300 hover:scale-105"
                  aria-label="Enviar mensaje"
                >
                  {isLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <ArrowUp className="h-4 w-4" />
                  )}
                </Button>
              </div>
            </form>
          </div>
        </div>
      </div>
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}
