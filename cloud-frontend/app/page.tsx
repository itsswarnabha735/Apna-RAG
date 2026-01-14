"use client";

import { useState, useRef, useEffect, FormEvent } from "react";

interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: string[];
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage = input.trim();
    setInput("");

    // Add user message
    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    setIsLoading(true);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userMessage }),
      });

      const data = await response.json();

      if (data.error) {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: `Error: ${data.error}` },
        ]);
      } else {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: data.answer,
            sources: data.sources,
          },
        ]);
      }
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Failed to connect to the server." },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="flex min-h-screen flex-col bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      {/* Header */}
      <header className="sticky top-0 z-10 bg-slate-900/80 backdrop-blur-md border-b border-slate-700/50 px-6 py-4">
        <div className="max-w-4xl mx-auto flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
            <span className="text-white text-lg">🧠</span>
          </div>
          <div>
            <h1 className="text-xl font-semibold text-white">Personal RAG</h1>
            <p className="text-sm text-slate-400">Your private knowledge assistant</p>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
              Connected
            </span>
          </div>
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-4xl mx-auto space-y-6">
          {messages.length === 0 && (
            <div className="text-center py-20">
              <div className="w-20 h-20 mx-auto mb-6 rounded-full bg-gradient-to-br from-indigo-500/20 to-purple-600/20 flex items-center justify-center">
                <span className="text-4xl">💬</span>
              </div>
              <h2 className="text-2xl font-semibold text-white mb-2">
                Ask me anything
              </h2>
              <p className="text-slate-400 max-w-md mx-auto">
                I have access to your personal documents. Ask questions about
                your files and I&apos;ll find the answers.
              </p>
            </div>
          )}

          {messages.map((message, index) => (
            <div
              key={index}
              className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] rounded-2xl px-5 py-3 ${message.role === "user"
                    ? "bg-indigo-600 text-white"
                    : "bg-slate-800/50 text-slate-100 border border-slate-700/50"
                  }`}
              >
                <p className="whitespace-pre-wrap">{message.content}</p>
                {message.sources && message.sources.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-slate-600/50">
                    <p className="text-xs text-slate-400 mb-1">Sources:</p>
                    <ul className="text-xs text-slate-500 space-y-0.5">
                      {message.sources.slice(0, 3).map((source, i) => (
                        <li key={i} className="truncate">
                          📄 {source.split("/").pop()}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          ))}

          {isLoading && (
            <div className="flex justify-start">
              <div className="bg-slate-800/50 rounded-2xl px-5 py-3 border border-slate-700/50">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce [animation-delay:-0.3s]"></div>
                  <div className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce [animation-delay:-0.15s]"></div>
                  <div className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce"></div>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input */}
      <div className="sticky bottom-0 border-t border-slate-700/50 bg-slate-900/80 backdrop-blur-md px-4 py-4">
        <form onSubmit={handleSubmit} className="max-w-4xl mx-auto">
          <div className="flex items-center gap-3 bg-slate-800 rounded-2xl px-4 py-3 border border-slate-700/50 focus-within:border-indigo-500/50 transition-colors">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about your documents..."
              className="flex-1 bg-transparent text-white placeholder-slate-400 focus:outline-none"
              disabled={isLoading}
            />
            <button
              type="submit"
              disabled={isLoading || !input.trim()}
              className="px-4 py-2 bg-gradient-to-r from-indigo-500 to-purple-600 text-white rounded-xl font-medium hover:from-indigo-600 hover:to-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
            >
              Send
            </button>
          </div>
        </form>
        <p className="text-center text-xs text-slate-500 mt-3">
          Powered by Gemini Flash • Local Data via Secure Tunnel
        </p>
      </div>
    </main>
  );
}
