"use client";

import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";

type ChatCardOption = {
  label: string;
  description: string;
  recommended?: boolean;
};

type ChatCardPayload = {
  title: string;
  subtitle?: string;
  bullets?: string[];
  options?: ChatCardOption[];
  actions?: string[];
};

type PmChatCardProps = {
  kind: string;
  card: ChatCardPayload;
  onOptionSelect?: (option: ChatCardOption) => void;
};

export default function PmChatCard({ kind, card, onOptionSelect }: PmChatCardProps) {
  return (
    <section className={`pm-embed-card is-${kind}`} aria-label={`${card.title} card`}>
      <header className="pm-embed-card-head">
        <strong>{card.title}</strong>
        {card.subtitle ? <span>{card.subtitle}</span> : null}
      </header>
      {card.bullets && card.bullets.length > 0 ? (
        <ul className="pm-embed-list">
          {card.bullets.map((bullet, index) => (
            <li key={`${bullet}-${index}`}>{bullet}</li>
          ))}
        </ul>
      ) : null}
      {card.options && card.options.length > 0 ? (
        <div className="pm-embed-options">
          {card.options.map((option, index) => (
            <button
              type="button"
              key={`${option.label}-${index}`}
              className={`pm-embed-option${onOptionSelect ? " is-clickable" : ""}`}
              onClick={onOptionSelect ? () => onOptionSelect(option) : undefined}
              aria-label={onOptionSelect ? `Use clarifier: ${option.label}` : undefined}
              title={onOptionSelect ? "Insert this clarifier into the composer" : undefined}
            >
              <div>
                <strong>{option.label}</strong>
                <p>{option.description}</p>
              </div>
              {option.recommended ? <Badge variant="running">Recommended</Badge> : null}
            </button>
          ))}
        </div>
      ) : null}
      {card.actions && card.actions.length > 0 ? (
        <div className="pm-embed-actions">
          {card.actions.map((action, index) => (
            <Button variant="ghost" key={`${action}-${index}`} disabled>
              {action}
            </Button>
          ))}
        </div>
      ) : null}
    </section>
  );
}
