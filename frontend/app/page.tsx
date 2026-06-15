"use client"; // Required for interactivity in Next.js App Router

import { useState, useRef, useEffect } from "react";

// 1. Define the base URL at the top of your file (outside the component)
// For local testing, keep localhost. 
// For production, we will change this via Environment Variables later.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";



export default function Home() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  // Auto-scroll to bottom ref
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  return (
    <main className="flex min-h-screen flex-col bg-gray-900 text-white">
      
      {/* 1. Header */}
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

      {/* 2. Chat Area (Constrained Width & Centered) */}
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
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
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
        {/* Invisible element to scroll to */}
        <div ref={messagesEndRef} />
      </div>

      {/* 3. Input Area (Fixed at bottom, Constrained Width) */}
      <div className="p-4 border-t border-gray-700 bg-gray-800 w-full">
        <div className="max-w-4xl mx-auto">
          
          {/* File Upload Section */}
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

          {/* Chat Input Section */}
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



  // --- Placeholder Functions (We will implement these next) ---
  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    // alert(`Upload triggered for: ${file.name}`);
    // TODO: Call API to upload

    setLoading(true); // Show loading state
    const formData = new FormData();
    formData.append("file", file);

    // // We need an API key. For now, let's prompt the user or hardcode it for testing.
    // // Ideally, you'd have a settings modal. Let's prompt for simplicity:
    // const apiKey = prompt("Please enter your Google Gemini API Key:");
    //     if (!apiKey) {
    //   alert("API Key is required!");
    //   setLoading(false);
    //   return;
    // }
    // formData.append("api_key", apiKey);

    try {
      console.log(`Attempting upload to ${API_BASE_URL}/upload...`);
      
      // const response = await fetch("http://localhost:8000/upload", {
      const response = await fetch(`${API_BASE_URL}/upload`, {
        method: "POST",
        body: formData,
        // Explicitly ensure no extra headers interfere
        // Fetch automatically sets 'Content-Type': 'multipart/form-data' with boundary
      });

      console.log("Response status:", response.status);

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: "Unknown error" }));
        throw new Error(errorData.detail || `Server error: ${response.status}`);
      }

      const data = await response.json();
      console.log("Upload success:", data);
      
      setSessionId(data.session_id);
      setMessages((prev) => [...prev, { 
        role: "assistant", 
        content: `Successfully loaded "${data.filename}". Ask me anything!` 
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

  async function handleSendMessage(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || !sessionId) return;

    const userMessage = input;
    setInput(""); // Clear input immediately
    setLoading(true);

    // 1. Add User Message to UI
    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);

    // 2. Prepare a placeholder for AI response
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

    try {
      const formData = new FormData();
      formData.append("session_id", sessionId);
      formData.append("query", userMessage);

      // 3. Call the Streaming Endpoint
      // const response = await fetch("http://localhost:8000/chat/stream", {
      const response = await fetch(`${API_BASE_URL}/chat/stream`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error("Failed to get response");
      }

      // 4. Read the Stream (Server-Sent Events)
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
          // Split by double newline (SSE format)
          const lines = chunk.split("\n\n");
          
          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const jsonStr = line.slice(6); // Remove "data: "
              try {
                const data = JSON.parse(jsonStr);
                
                // Append token if present
                if (data.token) {
                  aiText += data.token;
                  // Update the last message (the AI's placeholder)
                  setMessages((prev) => {
                    const newMsgs = [...prev];
                    newMsgs[newMsgs.length - 1] = { role: "assistant", content: aiText };
                    return newMsgs;
                  });
                }
                
                // Handle sources at the end
                if (data.done && data.sources) {
                  console.log("Sources received:", data.sources);
                  // Optional: Append sources to the message or show separately
                  // For now, we just finish the text
                }
                
                if (data.error) {
                  throw new Error(data.error);
                }
              } catch (parseErr) {
                // Ignore empty lines or parsing errors for partial chunks
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