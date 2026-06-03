import { useEffect, useState } from "react";
import { ChatProvider, useChatContext } from "./chat/ChatProvider";
import { Thread } from "./components/Thread";

export default function App() {
  return (
    <ChatProvider>
      <div className="flex h-dvh flex-col bg-gray-50">
        <Header />
        <main className="min-h-0 flex-1">
          <Thread />
        </main>
      </div>
    </ChatProvider>
  );
}

function Header() {
  const { newChat } = useChatContext();
  const [health, setHealth] = useState<{ model: string; frozen_now: string } | null>(null);

  useEffect(() => {
    fetch("/api/health")
      .then((response) => response.json())
      .then(setHealth)
      .catch(() => {});
  }, []);

  return (
    <header className="flex items-center gap-3 border-b border-gray-200 bg-white px-4 py-2.5">
      <span className="text-lg">🩺</span>
      <h1 className="text-sm font-semibold text-gray-800">Clinical Operations Assistant</h1>
      {health && (
        <span className="hidden rounded-full bg-gray-100 px-2.5 py-0.5 text-xs text-gray-500 sm:inline">
          {health.model} · now = {health.frozen_now.slice(0, 16).replace("T", " ")} UTC
        </span>
      )}
      <button
        type="button"
        onClick={newChat}
        className="ml-auto rounded-lg border border-gray-300 px-3 py-1 text-xs font-medium text-gray-600 hover:bg-gray-100"
      >
        New chat
      </button>
    </header>
  );
}
