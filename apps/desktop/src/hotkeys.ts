type PageKey = "overview" | "sessions" | "gates" | "review" | "settings";

export type HotkeyAction =
  | "overview"
  | "sessions"
  | "new_conversation"
  | "open_search"
  | "focus_input"
  | "focus_chain"
  | "toggle_sidebar"
  | "switch_recent_session"
  | "refresh"
  | "toggle_drawer"
  | "toggle_pin"
  | "toggle_layout_mode"
  | "open_chain_popout"
  | "page_by_number";

export type HotkeySpec = {
  action: HotkeyAction;
  combo: string;
  description: string;
};

export const desktopHotkeys: HotkeySpec[] = [
  { action: "new_conversation", combo: "Cmd/Ctrl+N", description: "Start a new conversation" },
  { action: "open_search", combo: "Cmd/Ctrl+K", description: "Open search (command palette)" },
  { action: "focus_input", combo: "Cmd/Ctrl+.", description: "Focus the message input" },
  { action: "focus_chain", combo: "Cmd/Ctrl+Shift+C", description: "Focus Command Chain" },
  { action: "toggle_sidebar", combo: "Cmd/Ctrl+Shift+S", description: "Show or hide the session sidebar" },
  { action: "switch_recent_session", combo: "Cmd/Ctrl+1..3", description: "Jump to the 3 most recent sessions" },
  { action: "toggle_layout_mode", combo: "Cmd/Ctrl+\\", description: "Toggle layout mode (dialog first / split)" },
  { action: "open_chain_popout", combo: "Cmd/Ctrl+Shift+D", description: "Open Command Chain in a separate window" },
  { action: "page_by_number", combo: "Alt+1..5", description: "Jump to the matching page" },
  { action: "overview", combo: "Alt+M", description: "Go to overview" },
  { action: "sessions", combo: "Alt+L", description: "Go to live sessions" },
  { action: "refresh", combo: "Alt+R", description: "Refresh data now" },
  { action: "toggle_drawer", combo: "Alt+D", description: "Show or hide the right drawer" },
  { action: "toggle_pin", combo: "Alt+P", description: "Pin or unpin the right drawer" }
];

type HotkeyResult =
  | { kind: "set_page"; page: PageKey }
  | { kind: "new_conversation" }
  | { kind: "open_search" }
  | { kind: "focus_input" }
  | { kind: "focus_chain" }
  | { kind: "toggle_sidebar" }
  | { kind: "switch_recent_session"; index: number }
  | { kind: "refresh" }
  | { kind: "toggle_drawer" }
  | { kind: "toggle_pin" }
  | { kind: "toggle_layout_mode" }
  | { kind: "open_chain_popout" }
  | { kind: "none" };

export function resolveHotkey(event: KeyboardEvent, pageOrder: PageKey[]): HotkeyResult {
  const metaOrCtrl = event.metaKey || event.ctrlKey;
  if (metaOrCtrl && !event.shiftKey && !event.altKey && event.key.toLowerCase() === "n") {
    return { kind: "new_conversation" };
  }
  if (metaOrCtrl && !event.shiftKey && !event.altKey && event.key.toLowerCase() === "k") {
    return { kind: "open_search" };
  }
  if (metaOrCtrl && !event.shiftKey && !event.altKey && event.key === ".") {
    return { kind: "focus_input" };
  }
  if (metaOrCtrl && event.shiftKey && !event.altKey && event.key.toLowerCase() === "c") {
    return { kind: "focus_chain" };
  }
  if (metaOrCtrl && event.shiftKey && !event.altKey && event.key.toLowerCase() === "s") {
    return { kind: "toggle_sidebar" };
  }
  if (metaOrCtrl && !event.shiftKey && !event.altKey && event.key >= "1" && event.key <= "3") {
    return { kind: "switch_recent_session", index: Number(event.key) - 1 };
  }
  if (metaOrCtrl && !event.shiftKey && !event.altKey && event.key === "\\") {
    return { kind: "toggle_layout_mode" };
  }
  if (metaOrCtrl && event.shiftKey && !event.altKey && event.key.toLowerCase() === "d") {
    return { kind: "open_chain_popout" };
  }

  if (!event.altKey || event.shiftKey || event.metaKey || event.ctrlKey) {
    return { kind: "none" };
  }

  if (event.key >= "1" && event.key <= "5") {
    const index = Number(event.key) - 1;
    const page = pageOrder[index];
    return page ? { kind: "set_page", page } : { kind: "none" };
  }

  const key = event.key.toLowerCase();
  if (key === "m") {
    return { kind: "set_page", page: "overview" };
  }
  if (key === "l") {
    return { kind: "set_page", page: "sessions" };
  }
  if (key === "r") {
    return { kind: "refresh" };
  }
  if (key === "d") {
    return { kind: "toggle_drawer" };
  }
  if (key === "p") {
    return { kind: "toggle_pin" };
  }
  return { kind: "none" };
}
