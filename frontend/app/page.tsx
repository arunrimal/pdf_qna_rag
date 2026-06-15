"use client";

import { useState, useRef, useEffect } from "react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Source = {
  page: string;
  snippet: string;
  score: number | string;
};

type Message = {
  role: string;
  content: string;
  sources?: Source[];
};

export default function Home() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [expandedSources, setExpandedSources] = useState<Set<number>>(new Set());

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const toggleSources = (idx: number) => {
    setExpandedSources((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  return (
    <main className="flex min-h-screen flex-col bg-gray-900 text-white">

      {/* Header */}
      <header className="p-4 border-b border-gray-700 bg-gray-800 shadow-md sticky top-0 z-10">
        <div className="max-w-4xl mx-auto flex justify-between items-center">
          <h1 className="text-xl font-bold text-blue-400">📄 PDF Q&A RAG</h1>
          {sessionId && (
            <span className="text-xs bg-green-900 text-green-300 px-2 py-1 rounded-full border border-green-700">
              ● Session Active
            </span>
          )}
        </div>
      </header>

      {/* Chat Area */}
      <div className="flex-1 overflow-y-auto p-4 w-full max-w-4xl mx-auto space-y-6">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-500 mt-20 space-y-4">
            <div className="text-6xl">🤖</div>
            <p className="text-lg">Upload a PDF to start chatting!</p>
          </div>
        ) : (
          messages.map((msg, idx) => (
            <div
              key={idx}
              className={`flex flex-col ${msg.role === "user" ? "items-end" : "items-start"}`}
            >
              <div
                className={`max-w-[85%] md:max-w-[75%] rounded-2xl p-4 shadow-lg ${
                  msg.role === "user"
                    ? "bg-blue-600 text-white rounded-br-none"
                    : "bg-gray-800 text-gray-100 border border-gray-700 rounded-bl-none"
                }`}
              >
                <p className="text-sm md:text-base leading-relaxed whitespace-pre-wrap">{msg.content}</p>
              </div>

              {/* Sources */}
              {msg.role === "assistant" && msg.sources && msg.sources.length > 0 && (
                <div className="max-w-[85%] md:max-w-[75%] mt-2">
                  <button
                    onClick={() => toggleSources(idx)}
                    className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 transition"
                  >
                    <span>{expandedSources.has(idx) ? "▾" : "▸"}</span>
                    {msg.sources.length} source{msg.sources.length > 1 ? "s" : ""}
                  </button>

                  {expandedSources.has(idx) && (
                    <div className="mt-2 space-y-2">
                      {msg.sources.map((src, sIdx) => (
                        <div
                          key={sIdx}
                          className="bg-gray-700 border border-gray-600 rounded-xl p-3 text-xs text-gray-300"
                        >
                          <div className="flex justify-between mb-1">
                            <span className="text-blue-300 font-medium">Page {src.page}</span>
                            <span className="text-gray-400">Score: {src.score}</span>
                          </div>
                          <p className="leading-relaxed italic">"{src.snippet}"</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))
        )}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-800 border border-gray-700 rounded-2xl rounded-bl-none p-4 shadow-lg">
              <div className="flex space-x-2">
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-100"></div>
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-200"></div>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-4 border-t border-gray-700 bg-gray-800 w-full">
        <div className="max-w-4xl mx-auto">

          {!sessionId && (
            <div className="flex justify-center py-4">
              <label className="cursor-pointer bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-700 hover:to-emerald-700 text-white font-medium px-6 py-3 rounded-full shadow-lg transition transform hover:scale-105 flex items-center gap-2">
                <span>📁</span> Upload PDF
                <input
                  type="file"
                  accept=".pdf"
                  className="hidden"
                  onChange={(e) => handleFileUpload(e)}
                  disabled={loading}
                />
              </label>
            </div>
          )}

          {sessionId && (
            <form onSubmit={handleSendMessage} className="flex gap-3 items-end">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask a question about your PDF..."
                className="flex-1 bg-gray-900 text-white border border-gray-700 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition shadow-inner"
                disabled={loading}
              />
              <button
                type="submit"
                disabled={loading || !input.trim()}
                className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:cursor-not-allowed text-white p-3 rounded-xl transition shadow-lg flex items-center justify-center"
              >
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-6 h-6">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
                </svg>
              </button>
            </form>
          )}

          <p className="text-center text-xs text-gray-500 mt-3">
            Powered by FastAPI, LlamaIndex & Gemini
          </p>
        </div>
      </div>
    </main>
  );

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    setLoading(true);
    const formData = new FormData();
    formData.append("file", file);

    try {
      console.log(`Attempting upload to ${API_BASE_URL}/upload...`);

      const response = await fetch(`${API_BASE_URL}/upload`, {
        method: "POST",
        body: formData,
      });

      console.log("Response status:", response.status);

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: "Unknown error" }));
        throw new Error(errorData.detail || `Server error: ${response.status}`);
      }

      const data = await response.json();
      console.log("Upload success:", data);

      setSessionId(data.session_id);
      setMessages([{
        role: "assistant",
        content: `Successfully loaded "${data.filename}". Ask me anything!`,
      }]);

    } catch (error: any) {
      console.error("Full error object:", error);
      let msg = "Failed to connect to backend.";
      if (error.message.includes("Failed to fetch")) {
        msg = `Could not connect to ${API_BASE_URL}. Is the server running? Check CORS.`;
      } else {
        msg = error.message;
      }
      alert(msg);
    } finally {
      setLoading(false);
    }
  }

  async function handleSendMessage(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!input.trim() || !sessionId) return;

    const userMessage = input;
    setInput("");
    setLoading(true);

    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

    try {
      const formData = new FormData();
      formData.append("session_id", sessionId);
      formData.append("query", userMessage);

      const response = await fetch(`${API_BASE_URL}/chat/stream`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) throw new Error("Failed to get response");

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) throw new Error("No reader available");

      let aiText = "";
      let done = false;

      while (!done) {
        const { value, done: streamDone } = await reader.read();
        done = streamDone;

        if (value) {
          const chunk = decoder.decode(value);
          const lines = chunk.split("\n\n");

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const jsonStr = line.slice(6);
              try {
                const data = JSON.parse(jsonStr);

                if (data.token) {
                  aiText += data.token;
                  setMessages((prev) => {
                    const newMsgs = [...prev];
                    newMsgs[newMsgs.length - 1] = { role: "assistant", content: aiText };
                    return newMsgs;
                  });
                }

                if (data.done) {
                  setMessages((prev) => {
                    const newMsgs = [...prev];
                    newMsgs[newMsgs.length - 1] = {
                      role: "assistant",
                      content: aiText,
                      sources: data.sources ?? [],
                    };
                    return newMsgs;
                  });
                }

                if (data.error) throw new Error(data.error);

              } catch (parseErr) {
                // ignore partial/empty chunks
              }
            }
          }
        }
      }

    } catch (error: any) {
      console.error(error);
      setMessages((prev) => {
        const newMsgs = [...prev];
        newMsgs[newMsgs.length - 1] = { role: "assistant", content: "❌ Error: " + error.message };
        return newMsgs;
      });
    } finally {
      setLoading(false);
    }
  }
}
