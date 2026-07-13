import { streamAction } from "../transport/streamAction";
import type { ChatSendActionFrame, DownFrame } from "../types";

export type ChatActionInput = Omit<ChatSendActionFrame, "data_type">;

export function runChatAction(
  input: ChatActionInput,
  onEvent: (frame: DownFrame) => void,
  signal?: AbortSignal,
): Promise<void> {
  return streamAction(
    { data_type: "chat.send", ...input },
    onEvent,
    signal,
  );
}
