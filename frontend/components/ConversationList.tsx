"use client";

import { Button } from "@/components/ui/button";
import { Trash2, Edit2, Download, MoreVertical, MessageSquare } from "lucide-react";
import { Conversation } from "@/lib/conversations";
import { useState } from "react";

interface ConversationListProps {
  conversations: Conversation[];
  currentConversationId: string | null;
  onSelectConversation: (conversationId: string) => void;
  onDeleteConversation: (conversationId: string) => void;
  onRenameConversation: (conversationId: string, newTitle: string) => void;
  onExportConversation: (conversation: Conversation, format: "markdown" | "pdf") => void;
}

export function ConversationList({
  conversations,
  currentConversationId,
  onSelectConversation,
  onDeleteConversation,
  onRenameConversation,
  onExportConversation,
}: ConversationListProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);

  const handleStartEdit = (conversation: Conversation) => {
    setEditingId(conversation.id);
    setEditTitle(conversation.title);
  };

  const handleSaveEdit = (conversationId: string) => {
    if (editTitle.trim()) {
      onRenameConversation(conversationId, editTitle.trim());
    }
    setEditingId(null);
    setEditTitle("");
  };

  const handleCancelEdit = () => {
    setEditingId(null);
    setEditTitle("");
  };

  const formatDate = (date: Date) => {
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    
    if (days === 0) {
      return "Today";
    } else if (days === 1) {
      return "Yesterday";
    } else if (days < 7) {
      return `${days} days ago`;
    } else {
      return date.toLocaleDateString("en-US", { day: "numeric", month: "short" });
    }
  };

  if (conversations.length === 0) {
    return (
      <div className="p-4 text-center text-sm text-muted-foreground">
        <MessageSquare className="h-8 w-8 mx-auto mb-2 opacity-50" />
        <p>No conversations</p>
        <p className="text-xs mt-1">Create a new one to get started</p>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {conversations.map((conversation) => {
        const isActive = conversation.id === currentConversationId;
        const isEditing = editingId === conversation.id;
        const isHovered = hoveredId === conversation.id;
        const isMenuOpen = menuOpenId === conversation.id;

        return (
          <div
            key={conversation.id}
            className={`group relative rounded-lg transition-colors ${
              isActive
                ? "bg-primary/10 border border-primary/20"
                : "hover:bg-muted/50 border border-transparent"
            }`}
            onMouseEnter={() => setHoveredId(conversation.id)}
            onMouseLeave={() => {
              setHoveredId(null);
              setMenuOpenId(null);
            }}
          >
            <div
              className={`flex items-center gap-2 p-2.5 cursor-pointer ${
                isActive ? "" : "hover:bg-muted/30"
              } rounded-lg`}
              onClick={() => !isEditing && onSelectConversation(conversation.id)}
            >
              {isEditing ? (
                <div className="flex-1 flex items-center gap-2">
                  <input
                    type="text"
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        handleSaveEdit(conversation.id);
                      } else if (e.key === "Escape") {
                        handleCancelEdit();
                      }
                    }}
                    onClick={(e) => e.stopPropagation()}
                    className="flex-1 px-2 py-1 text-sm bg-background border border-input rounded focus:outline-none focus:ring-2 focus:ring-ring"
                    autoFocus
                  />
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-6 w-6 p-0"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleSaveEdit(conversation.id);
                    }}
                  >
                    <span className="text-xs">✓</span>
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-6 w-6 p-0"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleCancelEdit();
                    }}
                  >
                    <span className="text-xs">✕</span>
                  </Button>
                </div>
              ) : (
                <>
                  <MessageSquare className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-foreground truncate">
                      {conversation.title}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {formatDate(conversation.updatedAt)}
                    </div>
                  </div>
                  {(isHovered || isMenuOpen) && (
                    <div className="flex items-center gap-1 shrink-0">
                      <div className="relative">
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 w-7 p-0"
                          onClick={(e) => {
                            e.stopPropagation();
                            setMenuOpenId(isMenuOpen ? null : conversation.id);
                          }}
                        >
                          <MoreVertical className="h-3.5 w-3.5" />
                        </Button>
                        {isMenuOpen && (
                          <div className="absolute right-0 top-8 z-50 w-48 bg-popover border border-border rounded-md shadow-lg py-1">
                            <button
                              className="w-full px-3 py-1.5 text-left text-sm hover:bg-muted flex items-center gap-2"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleStartEdit(conversation);
                                setMenuOpenId(null);
                              }}
                            >
                              <Edit2 className="h-3.5 w-3.5" />
                              Rename
                            </button>
                            <button
                              className="w-full px-3 py-1.5 text-left text-sm hover:bg-muted flex items-center gap-2"
                              onClick={(e) => {
                                e.stopPropagation();
                                onExportConversation(conversation, "markdown");
                                setMenuOpenId(null);
                              }}
                            >
                              <Download className="h-3.5 w-3.5" />
                              Export Markdown
                            </button>
                            <button
                              className="w-full px-3 py-1.5 text-left text-sm hover:bg-muted flex items-center gap-2"
                              onClick={(e) => {
                                e.stopPropagation();
                                onExportConversation(conversation, "pdf");
                                setMenuOpenId(null);
                              }}
                            >
                              <Download className="h-3.5 w-3.5" />
                              Export PDF
                            </button>
                            <div className="border-t border-border my-1" />
                            <button
                              className="w-full px-3 py-1.5 text-left text-sm text-destructive hover:bg-destructive/10 flex items-center gap-2"
                              onClick={(e) => {
                                e.stopPropagation();
                                if (confirm("Delete this conversation?")) {
                                  onDeleteConversation(conversation.id);
                                }
                                setMenuOpenId(null);
                              }}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                              Delete
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

