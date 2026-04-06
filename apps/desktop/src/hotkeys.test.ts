import { describe, expect, it } from "vitest";
import { resolveHotkey } from "./hotkeys";

type PageKey = "overview" | "sessions" | "gates" | "review" | "settings";

const pageOrder: PageKey[] = ["overview", "sessions", "gates", "review", "settings"];

function keyEvent(
  key: string,
  options: { altKey?: boolean; metaKey?: boolean; ctrlKey?: boolean; shiftKey?: boolean } = {}
): KeyboardEvent {
  return new KeyboardEvent("keydown", {
    key,
    altKey: options.altKey ?? false,
    metaKey: options.metaKey ?? false,
    ctrlKey: options.ctrlKey ?? false,
    shiftKey: options.shiftKey ?? false
  });
}

describe("resolveHotkey", () => {
  it("ignores non-alt keys", () => {
    expect(resolveHotkey(keyEvent("1"), pageOrder)).toEqual({ kind: "none" });
  });

  it("resolves meta layout and popout actions", () => {
    expect(resolveHotkey(keyEvent("\\", { metaKey: true }), pageOrder)).toEqual({ kind: "toggle_layout_mode" });
    expect(resolveHotkey(keyEvent("d", { ctrlKey: true, shiftKey: true }), pageOrder)).toEqual({
      kind: "open_chain_popout"
    });
  });

  it("resolves new conversation, search and focus actions", () => {
    expect(resolveHotkey(keyEvent("n", { metaKey: true }), pageOrder)).toEqual({ kind: "new_conversation" });
    expect(resolveHotkey(keyEvent("k", { ctrlKey: true }), pageOrder)).toEqual({ kind: "open_search" });
    expect(resolveHotkey(keyEvent(".", { metaKey: true }), pageOrder)).toEqual({ kind: "focus_input" });
    expect(resolveHotkey(keyEvent("c", { ctrlKey: true, shiftKey: true }), pageOrder)).toEqual({ kind: "focus_chain" });
    expect(resolveHotkey(keyEvent("s", { metaKey: true, shiftKey: true }), pageOrder)).toEqual({
      kind: "toggle_sidebar"
    });
  });

  it("resolves recent session switching", () => {
    expect(resolveHotkey(keyEvent("1", { metaKey: true }), pageOrder)).toEqual({
      kind: "switch_recent_session",
      index: 0
    });
    expect(resolveHotkey(keyEvent("3", { ctrlKey: true }), pageOrder)).toEqual({
      kind: "switch_recent_session",
      index: 2
    });
  });

  it("resolves page by number", () => {
    expect(resolveHotkey(keyEvent("1", { altKey: true }), pageOrder)).toEqual({ kind: "set_page", page: "overview" });
    expect(resolveHotkey(keyEvent("5", { altKey: true }), pageOrder)).toEqual({ kind: "set_page", page: "settings" });
  });

  it("returns none when number is out of mapped range", () => {
    const shortOrder: PageKey[] = ["overview", "sessions"];
    expect(resolveHotkey(keyEvent("3", { altKey: true }), shortOrder)).toEqual({ kind: "none" });
  });

  it("resolves explicit navigation and control actions", () => {
    expect(resolveHotkey(keyEvent("m", { altKey: true }), pageOrder)).toEqual({ kind: "set_page", page: "overview" });
    expect(resolveHotkey(keyEvent("l", { altKey: true }), pageOrder)).toEqual({ kind: "set_page", page: "sessions" });
    expect(resolveHotkey(keyEvent("r", { altKey: true }), pageOrder)).toEqual({ kind: "refresh" });
    expect(resolveHotkey(keyEvent("d", { altKey: true }), pageOrder)).toEqual({ kind: "toggle_drawer" });
    expect(resolveHotkey(keyEvent("p", { altKey: true }), pageOrder)).toEqual({ kind: "toggle_pin" });
  });

  it("returns none for unsupported hotkeys", () => {
    expect(resolveHotkey(keyEvent("x", { altKey: true }), pageOrder)).toEqual({ kind: "none" });
  });

  it("does not treat Alt+Shift combinations as global Alt actions", () => {
    expect(resolveHotkey(keyEvent("r", { altKey: true, shiftKey: true }), pageOrder)).toEqual({ kind: "none" });
    expect(resolveHotkey(keyEvent("d", { altKey: true, shiftKey: true }), pageOrder)).toEqual({ kind: "none" });
    expect(resolveHotkey(keyEvent("2", { altKey: true, shiftKey: true }), pageOrder)).toEqual({ kind: "none" });
  });
});
