import { useEffect, useId, useRef } from "react";
import { Button } from "../ui/Button";

type DiffReviewModalProps = {
  open: boolean;
  reviewDecision: "pending" | "accepted" | "rework";
  onClose: () => void;
  onAccept: () => void;
  onRework: () => void;
};

export function DiffReviewModal({
  open,
  reviewDecision,
  onClose,
  onAccept,
  onRework
}: DiffReviewModalProps) {
  const modalRef = useRef<HTMLDivElement | null>(null);
  const titleId = useId();
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  const getFocusableElements = () => {
    if (!modalRef.current) {
      return [];
    }
    return Array.from(
      modalRef.current.querySelectorAll<HTMLElement>(
        'button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])',
      ),
    ).filter((item) => !item.hasAttribute("disabled"));
  };

  useEffect(() => {
    if (!open) {
      return;
    }
    if (!previousFocusRef.current) {
      previousFocusRef.current = document.activeElement as HTMLElement | null;
    }
    const focusables = getFocusableElements();
    if (focusables.length > 0 && !modalRef.current?.contains(document.activeElement)) {
      focusables[0]?.focus();
    } else if (focusables.length === 0) {
      modalRef.current?.focus();
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key === "Tab" && modalRef.current) {
        const tabbables = getFocusableElements();
        if (tabbables.length === 0) {
          return;
        }
        const first = tabbables[0];
        const last = tabbables[tabbables.length - 1];
        const active = document.activeElement as HTMLElement | null;
        const activeInsideModal = Boolean(active && modalRef.current.contains(active));
        if (!activeInsideModal) {
          event.preventDefault();
          (event.shiftKey ? last : first)?.focus();
          return;
        }
        if (event.shiftKey && active === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && active === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      const previous = previousFocusRef.current;
      if (previous && document.contains(previous)) {
        previous.focus();
      }
      previousFocusRef.current = null;
    };
  }, [open]);

  if (!open) {
    return null;
  }
  return (
    <div ref={modalRef} className="overlay-modal" role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}>
      <article className="overlay-card diff-review-card">
        <header className="overlay-header">
          <h2 id={titleId}>Diff Review</h2>
          <Button variant="icon" onClick={onClose} aria-label="Close diff review">
            ×
          </Button>
        </header>
        <p>Default policy: review before merge. Current status: {reviewDecision === "pending" ? "Pending review" : reviewDecision === "accepted" ? "Accepted" : "Changes requested"}.</p>
        <ul className="file-list" aria-label="Diff file list">
          <li>apps/desktop/src/App.tsx</li>
          <li>apps/desktop/src/lib/desktopUi.tsx</li>
          <li>apps/desktop/src/hotkeys.ts</li>
        </ul>
        <pre className="raw-output" aria-label="Diff content preview">
{`+ Added node detail drawer
+ Added keyboard shortcuts contract
- Replaced report placeholder toasts`}
        </pre>
        <div className="quick-actions">
          <Button variant="primary" onClick={onAccept}>Accept and merge</Button>
          <Button variant="destructive" onClick={onRework}>Request changes</Button>
        </div>
      </article>
    </div>
  );
}
