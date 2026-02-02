"use client";

import { Conversation, getConversationStats } from "@/lib/conversations";
import { MessageSquare, User, Bot, FileText, Hash, Clock, TrendingUp } from "lucide-react";
import { Card } from "@/components/ui/card";

interface ConversationStatsProps {
  conversation: Conversation;
}

export function ConversationStats({ conversation }: ConversationStatsProps) {
  const stats = getConversationStats(conversation);

  const statItems = [
    {
      label: "Total mensajes",
      value: stats.totalMessages,
      icon: MessageSquare,
      color: "text-blue-500",
    },
    {
      label: "Mensajes usuario",
      value: stats.userMessages,
      icon: User,
      color: "text-green-500",
    },
    {
      label: "Mensajes asistente",
      value: stats.assistantMessages,
      icon: Bot,
      color: "text-purple-500",
    },
    {
      label: "Palabras totales",
      value: stats.totalWords.toLocaleString(),
      icon: FileText,
      color: "text-orange-500",
    },
    {
      label: "Tokens estimados",
      value: stats.estimatedTokens.toLocaleString(),
      icon: Hash,
      color: "text-pink-500",
    },
    {
      label: "Fuentes citadas",
      value: stats.totalSources,
      icon: FileText,
      color: "text-cyan-500",
    },
    {
      label: "Duración",
      value: stats.durationMinutes > 0 
        ? `${stats.durationMinutes} min` 
        : "< 1 min",
      icon: Clock,
      color: "text-indigo-500",
    },
    {
      label: "Promedio palabras/msg",
      value: stats.avgWordsPerMessage,
      icon: TrendingUp,
      color: "text-teal-500",
    },
  ];

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold text-foreground mb-3">Estadísticas</h3>
      <div className="grid grid-cols-2 gap-2">
        {statItems.map((item, idx) => {
          const Icon = item.icon;
          return (
            <Card
              key={idx}
              className="p-3 bg-card border border-border/50 hover:border-border transition-colors"
            >
              <div className="flex items-center gap-2">
                <Icon className={`h-4 w-4 ${item.color} shrink-0`} />
                <div className="flex-1 min-w-0">
                  <div className="text-xs text-muted-foreground truncate">
                    {item.label}
                  </div>
                  <div className="text-sm font-semibold text-foreground">
                    {item.value}
                  </div>
                </div>
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

