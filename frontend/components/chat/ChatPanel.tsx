"use client";

import { useState } from "react";
import { Send } from "lucide-react";

import type { ChatMessage } from "@/types";

export default function ChatPanel({ initialMessages }: { initialMessages: ChatMessage[] }) {
  const [messages, setMessages] = useState(initialMessages);
  const [draft, setDraft] = useState("");

  const send = () => {
    const content = draft.trim();
    if (!content) return;

    setMessages((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        role: "user",
        content,
        timestamp: new Date().toISOString(),
      },
      {
        id: crypto.randomUUID(),
        role: "assistant",
        content: "I'd suggest checking fuel and lodging around the next waypoint before the evening drive.",
        timestamp: new Date().toISOString(),
      },
    ]);
    setDraft("");
  };

  return (
    <section className="rounded-3xl border border-white/70 bg-white/80 p-6 shadow-glow backdrop-blur-xl">
      <h2 className="text-xl font-bold">Trip Chat</h2>
      <div className="mt-4 flex h-[320px] flex-col rounded-3xl border border-slate-200 bg-slate-50 p-4 sm:h-[420px]">
        <div className="flex-1 space-y-3 overflow-y-auto pr-1">
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}
        </div>
        <div className="mt-4 flex items-center gap-2 rounded-2xl border border-slate-200 bg-white p-2">
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && send()}
            placeholder="Ask about stops, weather, or budget..."
            className="min-w-0 flex-1 bg-transparent px-3 py-2 text-sm outline-none placeholder:text-slate-400"
          />
          <button
            onClick={send}
            className="inline-flex items-center gap-2 rounded-xl bg-ink px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800"
          >
            <Send className="h-4 w-4" />
            Send
          </button>
        </div>
      </div>
    </section>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[82%] rounded-2xl px-4 py-3 text-sm leading-6 ${
          isUser ? "bg-ink text-white" : "bg-white text-slate-700 shadow-sm"
        }`}
      >
        <div className="mb-1 text-[11px] uppercase tracking-[0.18em] opacity-70">
          {isUser ? "You" : "Planner AI"}
        </div>
        {message.content}
      </div>
    </div>
  );
}

