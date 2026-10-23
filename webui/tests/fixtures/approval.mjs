export function approvalFrame(callId = "call-1", name = "write_file") {
  return {
    type: "approval_request",
    approval_id: `approval-${callId}`,
    session_id: "session-1",
    call_id: callId,
    name,
    reason: name,
    workspace: "/workspace",
    paths: ["/outside.txt"],
    outside_paths: ["/outside.txt"],
    arguments: { path: "/outside.txt", content: "hello" },
  };
}
