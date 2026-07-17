import { useCallback, useEffect, useLayoutEffect, useMemo, useRef } from "react";
import { ConversationEventStream } from "../conversations/eventStream";
import { ConversationBridge } from "./conversationBridge";
import type { DebugFrame } from "../types";

function readStoredSeq(conversationId: string) {
  const raw = sessionStorage.getItem(`conv_seq_${conversationId}`);
  const parsed = raw ? parseInt(raw, 10) : 0;
  return Number.isFinite(parsed) ? parsed : 0;
}

export function useConversationSkillHost(options: {
  conversationId: string;
  skillId: string | null;
  onDebug?: (frame: DebugFrame) => void;
  onLoadingChange?: (loading: boolean) => void;
}) {
  const { conversationId, skillId, onDebug, onLoadingChange } = options;
  const bridgeRef = useRef<ConversationBridge | null>(null);
  const streamRef = useRef<ConversationEventStream | null>(null);
  const revisionRef = useRef(0);
  const iframeRef = useRef<HTMLIFrameElement | null>(null);

  const uiInstanceId = useMemo(
    () => (skillId ? `ui_${skillId}_${conversationId}` : ""),
    [skillId, conversationId],
  );

  useLayoutEffect(() => {
    if (!skillId) {
      bridgeRef.current?.dispose();
      bridgeRef.current = null;
      return;
    }

    const bridge = new ConversationBridge({
      conversationId,
      skillId,
      uiInstanceId,
      onDebug: onDebug || (() => {}),
      onLoadingChange,
      getRevision: () => revisionRef.current,
      setRevision: (value) => {
        revisionRef.current = value;
      },
    });
    bridgeRef.current = bridge;
    bridge.setIframe(iframeRef.current);
    return () => {
      bridge.dispose();
      if (bridgeRef.current === bridge) {
        bridgeRef.current = null;
      }
    };
  }, [conversationId, onDebug, onLoadingChange, skillId, uiInstanceId]);

  useEffect(() => {
    if (!skillId || !conversationId) {
      streamRef.current?.stop();
      streamRef.current = null;
      return;
    }

    const stream = new ConversationEventStream(
      conversationId,
      (event) => {
        void bridgeRef.current?.handleConversationEvent(event);
        sessionStorage.setItem(`conv_seq_${conversationId}`, String(event.conversationSeq));
      },
      (error) => console.error("Conversation SSE error:", error),
    );
    streamRef.current = stream;
    stream.start(readStoredSeq(conversationId));
    return () => stream.stop();
  }, [conversationId, skillId]);

  const bindIframe = useCallback((iframe: HTMLIFrameElement | null) => {
    iframeRef.current = iframe;
    bridgeRef.current?.setIframe(iframe);
  }, []);

  return { bindIframe, uiInstanceId, conversationId };
}

export function buildSkillUiUrl(
  appId: string,
  conversationId: string,
  uiInstanceId: string,
  extraQuery = "",
) {
  const base =
    `/api/apps/${encodeURIComponent(appId)}/ui/index.html` +
    `?conversationId=${encodeURIComponent(conversationId)}` +
    `&uiInstanceId=${encodeURIComponent(uiInstanceId)}`;
  return extraQuery ? `${base}&${extraQuery}` : base;
}
