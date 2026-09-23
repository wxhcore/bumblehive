import type { ApprovalMode } from "../types/api";

const STORAGE_KEY = "bumblehive.approval-mode.v1";

export function readApprovalMode(): ApprovalMode {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "full_access"
      ? "full_access"
      : "request";
  } catch {
    return "request";
  }
}

export function writeApprovalMode(mode: ApprovalMode): void {
  window.localStorage.setItem(STORAGE_KEY, mode);
}
