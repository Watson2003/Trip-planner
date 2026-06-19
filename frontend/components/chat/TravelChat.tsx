"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { MessageCircle, Send, X } from "lucide-react";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
};

interface TravelChatProps {
  tripId: string;
}

const QUICK_REPLIES = ["What to pack?", "Best time to visit", "Safety tips", "Local cuisine"];
const CHAT_WS_URL = process.env.NEXT_PUBLIC_CHAT_WS_URL ?? "ws://localhost:8000/api/chat/ws";

function createMessage(role: Message["role"], content: string, streaming = false): Message {
  return {
    id: crypto.randomUUID(),
    role,
    content,
    streaming,
  };
}

export default function TravelChat({ tripId }: TravelChatProps) {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([
    createMessage("assistant", "Ask me anything about the planned trip. I can help with packing, safety, food, or timing."),
  ]);
  const socketRef = useRef<WebSocket | null>(null);
  const pendingAssistantId = useRef<string | null>(null);
  const sessionId = useMemo(() => crypto.randomUUID(), []);

  useEffect(() => {
    if (!open) return;

    const socket = new WebSocket(CHAT_WS_URL);
    socketRef.current = socket;

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data as string) as { type: string; content?: string };
        if (payload.type === "token" && payload.content) {
          setMessages((current) =>
            current.map((message) =>
              message.id === pendingAssistantId.current
                ? { ...message, content: `${message.content}${payload.content}`, streaming: true }
                : message,
            ),
          );
        }

        if (payload.type === "done") {
          setMessages((current) =>
            current.map((message) =>
              message.id === pendingAssistantId.current ? { ...message, streaming: false } : message,
            ),
          );
          pendingAssistantId.current = null;
        }

        if (payload.type === "error" && payload.content) {
          setMessages((current) => [...current, createMessage("assistant", `Chat error: ${payload.content}`)]);
          pendingAssistantId.current = null;
        }
      } catch {
        // Ignore malformed payloads to keep the widget resilient.
      }
    };

    socket.onerror = () => {
      setMessages((current) => [...current, createMessage("assistant", "Connection error. Please try again.")]);
    };

    socket.onclose = () => {
      socketRef.current = null;
    };

    return () => {
      socket.close();
      socketRef.current = null;
    };
  }, [open]);

  const sendMessage = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;

    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      setMessages((current) => [
        ...current,
        createMessage("assistant", "Chat is connecting. Please try again in a moment."),
      ]);
      return;
    }

    const userMessage = createMessage("user", trimmed);
    const assistantMessage = createMessage("assistant", "", true);
    pendingAssistantId.current = assistantMessage.id;

    setMessages((current) => [...current, userMessage, assistantMessage]);
    setInput("");

    socket.send(
      JSON.stringify({
        session_id: sessionId,
        message: trimmed,
        trip_context: {
          trip_id: tripId,
        },
      }),
    );
  };

  return (
    <div className="fixed bottom-5 right-5 z-50">
      {open ? (
        <div className="mb-3 flex h-[70vh] w-[min(22rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-2xl">
          <div className="flex items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-3 text-slate-950">
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Travel Assistant</p>
              <h3 className="font-semibold">RoadMind AI</h3>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded-full p-2 transition hover:bg-slate-100"
              aria-label="Close chat"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex-1 space-y-3 overflow-y-auto bg-slate-50 p-4">
            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-6 shadow-sm ${
                    message.role === "user"
                      ? "bg-[#0071e3] text-white"
                      : "border border-slate-200 bg-white text-slate-950"
                  }`}
                >
                  {message.content || (message.streaming ? "Typing..." : "")}
                  {message.streaming ? <span className="ml-1 inline-block animate-pulse">▍</span> : null}
                </div>
              </div>
            ))}
          </div>

          <div className="border-t border-slate-200 bg-white p-3">
            <div className="mb-3 flex flex-wrap gap-2">
              {QUICK_REPLIES.map((reply) => (
                <button
                  key={reply}
                  type="button"
                  onClick={() => sendMessage(reply)}
                  className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-600 transition hover:border-blue-200 hover:bg-slate-100 hover:text-slate-950"
                >
                  {reply}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2">
              <input
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    sendMessage(input);
                  }
                }}
                placeholder="Ask about packing, safety, food..."
                className="min-w-0 flex-1 bg-transparent px-2 py-1 text-sm text-slate-950 outline-none placeholder:text-slate-400"
              />
              <button
                type="button"
                onClick={() => sendMessage(input)}
                className="inline-flex items-center gap-2 rounded-xl bg-[#0071e3] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#0077ed]"
              >
                <Send className="h-4 w-4" />
                Send
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="inline-flex items-center gap-2 rounded-full bg-[#0071e3] px-5 py-4 text-sm font-semibold text-white shadow-lg transition hover:-translate-y-0.5 hover:bg-[#0077ed]"
      >
        <MessageCircle className="h-4 w-4" />
        {open ? "Close Chat" : "Ask RoadMind"}
      </button>
    </div>
  );
}
