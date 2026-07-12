import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { useWebSocket } from "../hooks/useWebSocket";
import { NameInput } from "../components/NameInput";
import { SessionSidebar } from "../components/SessionSidebar";
import { ChatMessages, type ChatMsg, type DebugEvent } from "../components/ChatMessages";
import { ChatInput } from "../components/ChatInput";
import { MiniappOverlay } from "../components/MiniappOverlay";
import { ChatDebugModal } from "../components/ChatDebugModal";

const WS_URL = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;

function getCookie(name: string): string {
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return m ? decodeURIComponent(m[1]) : "";
}

function setCookie(name: string, value: string, days = 365) {
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=${days * 86400}`;
}

interface Session {
  session_id: string;
  title: string;
  updated_at: number;
  round_count: number;
}

let msgCounter = 0;

export function ChatPage() {
  const [username, setUsername] = useState(() => getCookie("chat_username"));
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [overlay, setOverlay] = useState<{ appId: string; sessionId: string } | null>(null);
  const [debugMsg, setDebugMsg] = useState<ChatMsg | null>(null);

  const streamBuf = useRef<ChatMsg | null>(null);
  const streamEvents = useRef<DebugEvent[]>([]);
  const requestIdRef = useRef("");

  const onDown = useCallback((data: any) => {
    const dt = data.data_type || data.type;
    if (dt !== "chat.event") return;
    const ev = data.data;

    if (ev.type !== "done") {
      streamEvents.current.push({
        type: ev.type,
        payload: ev.payload,
        ts: ev.ts,
      });
    }

    const updateStreamMsg = () => {
      const snapshot = streamBuf.current ? { ...streamBuf.current } : null;
      if (!snapshot) return;
      setMessages((prev) => {
        const copy = [...prev];
        const last = copy[copy.length - 1];
        if (last && last.id === snapshot.id) {
          copy[copy.length - 1] = snapshot;
        }
        return copy;
      });
    };

    const ensureBuf = () => {
      if (!streamBuf.current) {
        streamBuf.current = {
          id: `msg-${++msgCounter}`,
          role: "assistant",
          content: "",
          events: [],
        };
        const newMsg = streamBuf.current;
        setMessages((prev) => [...prev, newMsg]);
        setStreaming(false);
      }
    };

    if (ev.type === "text") {
      const delta = ev.payload?.delta || "";
      ensureBuf();
      streamBuf.current!.content += delta;
      updateStreamMsg();
    } else if (ev.type === "tool_call" && ev.payload?.name === "show_miniapp_entry") {
      const appId = ev.payload?.arguments?.app_id || "";
      if (appId) {
        ensureBuf();
        streamBuf.current!.loadedSkill = appId;
        updateStreamMsg();
      }
    } else if (ev.type === "done") {
      if (streamBuf.current) {
        streamBuf.current.roundIdx = ev.payload?.roundIdx;
        streamBuf.current.events = [...streamEvents.current];
        updateStreamMsg();
      }
      streamBuf.current = null;
      streamEvents.current = [];
      setStreaming(false);
    }
  }, []);

  const ws = useWebSocket(WS_URL, onDown);

  const refreshSessions = useCallback(async () => {
    if (!username) return;
    const list = await api.listChatSessions(username);
    setSessions(list);
  }, [username]);

  useEffect(() => {
    refreshSessions();
  }, [refreshSessions]);

  const loadHistory = useCallback(async (sessionId: string) => {
    const hist = await api.getChatHistory(sessionId);
    const msgs: ChatMsg[] = hist.map((h: any) => {
      if (h.role === "miniapp") {
        return {
          id: `msg-${++msgCounter}`,
          role: "miniapp" as const,
          content: h.summary || "",
          appId: h.appId,
          roundCount: h.rounds,
          miniappMessages: h.messages || [],
        };
      }
      return {
        id: `msg-${++msgCounter}`,
        role: h.role as "user" | "assistant",
        content: h.content,
        roundIdx: h.roundIdx,
      };
    });
    setMessages(msgs);
  }, []);

  const selectSession = useCallback(
    (id: string) => {
      setActiveSessionId(id);
      loadHistory(id);
    },
    [loadHistory],
  );

  const createSession = useCallback(async () => {
    if (!username) return;
    const res = await api.createChatSession(username, "新对话");
    await refreshSessions();
    setActiveSessionId(res.session_id);
    setMessages([]);
  }, [username, refreshSessions]);

  const deleteSession = useCallback(
    async (id: string) => {
      await api.deleteChatSession(id);
      if (activeSessionId === id) {
        setActiveSessionId(null);
        setMessages([]);
      }
      refreshSessions();
    },
    [activeSessionId, refreshSessions],
  );

  const handleLogin = useCallback((name: string) => {
    setCookie("chat_username", name);
    setUsername(name);
  }, []);

  const handleLogout = useCallback(() => {
    setCookie("chat_username", "", -1);
    setUsername("");
    setSessions([]);
    setActiveSessionId(null);
    setMessages([]);
  }, []);

  const sendMessage = useCallback(
    (text: string) => {
      if (!activeSessionId || streaming) return;
      const userMsg: ChatMsg = {
        id: `msg-${++msgCounter}`,
        role: "user",
        content: text,
      };
      setMessages((prev) => [...prev, userMsg]);
      setStreaming(true);

      const rid = `chat_${Date.now()}`;
      requestIdRef.current = rid;
      ws.send({
        data_type: "chat.send",
        sessionId: activeSessionId,
        intent: text,
        username,
        requestId: rid,
      });
    },
    [activeSessionId, streaming, username, ws],
  );

  const handleSkillClick = useCallback(
    (skillName: string) => {
      if (!activeSessionId) return;
      setOverlay({ appId: skillName, sessionId: activeSessionId });
    },
    [activeSessionId],
  );

  if (!username) {
    return <NameInput onSubmit={handleLogin} />;
  }

  return (
    <div style={styles.page}>
      <SessionSidebar
        sessions={sessions}
        activeId={activeSessionId}
        username={username}
        onSelect={selectSession}
        onCreate={createSession}
        onDelete={deleteSession}
        onLogout={handleLogout}
      />
      <div style={styles.main}>
        {activeSessionId ? (
          <>
            <ChatMessages
              messages={messages}
              streaming={streaming}
              onSkillClick={handleSkillClick}
              onDebug={setDebugMsg}
            />
            <ChatInput onSend={sendMessage} disabled={streaming} />
          </>
        ) : (
          <div style={styles.placeholder}>
            <div style={styles.placeholderIcon}>💬</div>
            <div style={styles.placeholderText}>选择一个对话或创建新对话</div>
          </div>
        )}
      </div>
      {overlay && (
        <MiniappOverlay
          appId={overlay.appId}
          sessionId={overlay.sessionId}
          onClose={async () => {
            await api.exitApp(overlay.appId, overlay.sessionId).catch(() => {});
            setOverlay(null);
            if (activeSessionId) loadHistory(activeSessionId);
          }}
        />
      )}
      {debugMsg && activeSessionId && (
        <ChatDebugModal
          msg={debugMsg}
          sessionId={activeSessionId}
          onClose={() => setDebugMsg(null)}
        />
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    height: "100vh", width: "100vw",
    display: "flex",
    background: "#fff",
    fontFamily: '"PingFang SC", system-ui, sans-serif',
  },
  main: {
    flex: 1,
    display: "flex", flexDirection: "column",
    overflow: "hidden",
  },
  placeholder: {
    flex: 1, display: "flex", flexDirection: "column",
    alignItems: "center", justifyContent: "center",
    color: "#ccc",
  },
  placeholderIcon: { fontSize: 56, marginBottom: 16 },
  placeholderText: { fontSize: 16, color: "#bbb" },
};
