import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

export type CardVariant = "default" | "metric" | "table" | "detail" | "compact" | "unstyled";

function cn(...parts: Array<string | undefined | null | false>): string {
  return parts.filter(Boolean).join(" ");
}

export const cardVariants = cva("", {
  variants: {
    variant: {
      default: "ui-card ui-card--default",
      metric: "ui-card ui-card--metric metric-card",
      table: "ui-card ui-card--table table-card",
      detail: "ui-card ui-card--detail detail-card",
      compact: "ui-card ui-card--compact compact-status-card",
      unstyled: "",
    } satisfies Record<CardVariant, string>,
  },
  defaultVariants: {
    variant: "default",
  },
});

const legacyCardVariants: Record<CardVariant, string> = {
  default: "card",
  metric: "metric-card",
  table: "card table-card",
  detail: "card detail-card",
  compact: "card compact-status-card",
  unstyled: "",
};

export type CardProps = React.HTMLAttributes<HTMLDivElement> &
  VariantProps<typeof cardVariants> & {
    asChild?: boolean;
  };

export const Card = React.forwardRef<HTMLDivElement, CardProps>(function Card(
  { className, variant, asChild = false, ...props },
  ref,
) {
  const Comp = asChild ? Slot : "div";
  const resolvedVariant = variant ?? "default";
  return (
    <Comp
      ref={ref}
      className={cn(cardVariants({ variant: resolvedVariant }), legacyCardVariants[resolvedVariant], className)}
      data-ui-primitive={resolvedVariant === "unstyled" ? undefined : "card"}
      data-ui-variant={resolvedVariant === "unstyled" ? undefined : resolvedVariant}
      {...props}
    />
  );
});

type CardSlotProps = React.HTMLAttributes<HTMLDivElement>;

export const CardHeader = React.forwardRef<HTMLDivElement, CardSlotProps>(function CardHeader(
  { className, ...props },
  ref,
) {
  return <div ref={ref} className={cn("ui-card__header card-header", className)} data-ui-primitive="card-header" {...props} />;
});

export const CardContent = React.forwardRef<HTMLDivElement, CardSlotProps>(function CardContent(
  { className, ...props },
  ref,
) {
  return <div ref={ref} className={cn("ui-card__content card-body", className)} data-ui-primitive="card-content" {...props} />;
});

export const CardFooter = React.forwardRef<HTMLDivElement, CardSlotProps>(function CardFooter(
  { className, ...props },
  ref,
) {
  return <div ref={ref} className={cn("ui-card__footer card-footer", className)} data-ui-primitive="card-footer" {...props} />;
});
