"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import Link from "next/link";
import { setupApi, subscriptionsApi } from "@/lib/api";
import type { SetupSession } from "@/lib/api";

const WELCOME_MESSAGE =
  "Welcome to Roxi setup. I'll ask you a few questions to understand what you sell and who your best customers are. This usually takes 5-10 minutes.\n\nTo start: what do you sell, and who typically buys it?";

function LoadingDots() {
  return (
    <span className="inline-flex gap-1 items-center">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-1.5 h-1.5 bg-ink-soft rounded-full animate-bounce"
          style={{ animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </span>
  );
}

type Message = {
  role: "user" | "assistant";
  content: string;
};

export default function SetupPage() {
  const [messages, setMessages] = useState<Message[]>([
    { role: "assistant", content: WELCOME_MESSAGE },
  ]);
  const [inputText, setInputText] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionState, setSessionState] = useState<"active" | "complete">("active");
  const [initError, setInitError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading, scrollToBottom]);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [inputText]);

  useEffect(() => {
    async function initSession() {
      try {
        const storedId = localStorage.getItem("roxi_setup_session_id");

        if (storedId) {
          try {
            const session = await setupApi.getSession(storedId);
            setSessionId(session.id);
            setSessionState(session.state);
            if (session.messages.length > 0) {
              setMessages(
                session.messages.map((m) => ({ role: m.role, content: m.content }))
              );
            }
            return;
          } catch {
            // stored session invalid — fall through to create new
            localStorage.removeItem("roxi_setup_session_id");
          }
        }

        // Need a subscription to attach the session to
        const subs = await subscriptionsApi.list();
        const sub = subs[0];
        if (!sub) {
          setInitError("No subscription found. Please contact support.");
          return;
        }

        const session = await setupApi.createSession(sub.id);
        localStorage.setItem("roxi_setup_session_id", session.id);
        setSessionId(session.id);
        setSessionState(session.state);
      } catch (err) {
        setInitError((err as Error).message || "Failed to start setup session.");
      }
    }

    initSession();
  }, []);

  async function handleSend() {
    const text = inputText.trim();
    if (!text || loading || !sessionId) return;

    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInputText("");
    setLoading(true);

    try {
      const result = await setupApi.sendMessage(sessionId, text);
      const lastAssistantMsg = result.messages
        .filter((m) => m.role === "assistant")
        .at(-1);

      if (lastAssistantMsg) {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: lastAssistantMsg.content },
        ]);
      }

      setSessionState(result.state);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Something went wrong: ${(err as Error).message}. Please try again.`,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  if (initError) {
    return (
      <div className="flex items-center justify-center min-h-64">
        <div className="bg-panel border border-rule rounded-sm p-6 max-w-sm text-center">
          <p className="text-sm font-mono text-red-600 mb-3">{initError}</p>
          <button
            onClick={() => window.location.reload()}
            className="text-xs font-mono text-ink-soft underline underline-offset-2 hover:text-ink"
          >
            retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)]">
      {/* Header */}
      <div className="shrink-0 border-b border-rule px-4 py-3 flex items-center justify-between bg-panel">
        <h1 className="font-mono text-sm font-medium text-ink">Roxi Setup</h1>
        {sessionState === "complete" && (
          <span className="text-xs font-mono text-teal bg-teal-wash px-2 py-0.5 rounded">
            complete
          </span>
        )}
        {sessionState === "active" && (
          <span className="text-xs font-mono text-ink-soft">
            {sessionId ? "session active" : "starting…"}
          </span>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-lg rounded-sm px-4 py-3 text-sm font-mono leading-relaxed whitespace-pre-wrap ${
                msg.role === "user"
                  ? "bg-teal text-white"
                  : "bg-panel border border-rule text-ink"
              }`}
            >
              {msg.content}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-panel border border-rule rounded-sm px-4 py-3">
              <LoadingDots />
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Completion banner */}
      {sessionState === "complete" && (
        <div className="shrink-0 mx-4 mb-3 bg-teal-wash border border-teal p-4 rounded-sm">
          <p className="text-sm font-mono text-teal font-medium mb-1">
            Configuration ready
          </p>
          <p className="text-xs font-mono text-teal/80 mb-3">
            Your configuration is ready. Roxi will start looking for leads using your targeting rules.
          </p>
          <Link
            href="/leads"
            className="inline-block text-xs font-mono bg-teal text-white px-3 py-1.5 rounded-sm hover:bg-teal/90 transition-colors"
          >
            View leads →
          </Link>
        </div>
      )}

      {/* Input row */}
      {sessionState === "active" && (
        <div className="shrink-0 border-t border-rule bg-panel px-4 py-3">
          <div className="flex gap-2 items-end">
            <textarea
              ref={textareaRef}
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Type your answer… (Enter to send, Shift+Enter for newline)"
              rows={1}
              disabled={loading || !sessionId}
              className="flex-1 resize-none px-3 py-2 text-sm font-mono bg-ground border border-rule rounded-sm text-ink placeholder:text-ink-soft focus:outline-none focus:border-teal disabled:opacity-50 overflow-hidden"
            />
            <button
              onClick={handleSend}
              disabled={loading || !inputText.trim() || !sessionId}
              className="shrink-0 px-4 py-2 text-sm font-mono bg-teal text-white rounded-sm hover:bg-teal/90 disabled:opacity-50 transition-colors"
            >
              Send
            </button>
          </div>
          <p className="text-xs font-mono text-ink-soft mt-1.5">
            Enter to send · Shift+Enter for newline
          </p>
        </div>
      )}
    </div>
  );
}
