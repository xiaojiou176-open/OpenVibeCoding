"use client";

import { useEffect, type Dispatch, type RefObject, type SetStateAction } from "react";

type PMLayoutMode = "dialog" | "split" | "chain" | "focus";

type UsePMLayoutShortcutsParams = {
  chatFlowBusy: boolean;
  layoutMode: PMLayoutMode;
  setLayoutMode: Dispatch<SetStateAction<PMLayoutMode>>;
  onStartNewConversation: () => Promise<void>;
  chatInputRef: RefObject<HTMLTextAreaElement | null>;
  chainPanelRef: RefObject<HTMLElement | null>;
};

export function usePMLayoutShortcuts({
  chatFlowBusy,
  layoutMode,
  setLayoutMode,
  onStartNewConversation,
  chatInputRef,
  chainPanelRef,
}: UsePMLayoutShortcutsParams): void {
  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const handleLayoutShortcut = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const editable =
        target?.isContentEditable ||
        target?.tagName === "INPUT" ||
        target?.tagName === "TEXTAREA" ||
        target?.tagName === "SELECT";
      if (editable || (!event.metaKey && !event.ctrlKey)) {
        return;
      }

      if (event.key === "n" || event.key === "N") {
        event.preventDefault();
        if (!chatFlowBusy) {
          void onStartNewConversation();
        }
        return;
      }

      if (event.key === ".") {
        event.preventDefault();
        chatInputRef.current?.focus();
        return;
      }

      if (event.shiftKey && event.key.toLowerCase() === "c") {
        event.preventDefault();
        if (layoutMode === "dialog" || layoutMode === "focus") {
          setLayoutMode("split");
        }
        chainPanelRef.current?.focus();
        return;
      }

      if (event.key === "\\") {
        event.preventDefault();
        setLayoutMode((current) => (current === "split" ? "dialog" : "split"));
        return;
      }

      if (event.shiftKey && event.key.toLowerCase() === "d") {
        event.preventDefault();
        setLayoutMode((current) => (current === "chain" ? "split" : "chain"));
      }
    };

    window.addEventListener("keydown", handleLayoutShortcut);
    return () => window.removeEventListener("keydown", handleLayoutShortcut);
  }, [chatFlowBusy, layoutMode, setLayoutMode, onStartNewConversation, chatInputRef, chainPanelRef]);
}
