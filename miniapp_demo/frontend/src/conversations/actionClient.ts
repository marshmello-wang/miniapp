import type { SubmitActionRequest, ViewSnapshotPayload } from "./types";

const base = (conversationId: string) =>
  `/api/conversations/${encodeURIComponent(conversationId)}`;

export async function submitAction(
  conversationId: string,
  body: SubmitActionRequest,
): Promise<Record<string, unknown>> {
  const response = await fetch(`${base(conversationId)}/actions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Action failed: HTTP ${response.status} ${detail}`.trim());
  }
  return response.json();
}

export async function submitSnapshot(
  conversationId: string,
  actionId: string,
  body: ViewSnapshotPayload,
): Promise<void> {
  const response = await fetch(
    `${base(conversationId)}/actions/${encodeURIComponent(actionId)}/snapshot`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Snapshot failed: HTTP ${response.status} ${detail}`.trim());
  }
}

export async function cancelAction(
  conversationId: string,
  actionId: string,
): Promise<void> {
  const response = await fetch(
    `${base(conversationId)}/actions/${encodeURIComponent(actionId)}/cancel`,
    { method: "POST" },
  );
  if (!response.ok) {
    throw new Error(`Cancel failed: HTTP ${response.status}`);
  }
}
