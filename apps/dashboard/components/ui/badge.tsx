import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

export type BadgeVariant = "default" | "success" | "warning" | "failed" | "running" | "unstyled";

function cn(...parts: Array<string | undefined | null | false>): string {
  return parts.filter(Boolean).join(" ");
}

export const badgeVariants = cva("", {
  variants: {
    variant: {
      default: "ui-badge ui-badge--default",
      success: "ui-badge ui-badge--success",
      warning: "ui-badge ui-badge--warning",
      failed: "ui-badge ui-badge--failed",
      running: "ui-badge ui-badge--running",
      unstyled: "",
    } satisfies Record<BadgeVariant, string>,
  },
  defaultVariants: {
    variant: "default",
  },
});

const legacyBadgeVariants: Record<BadgeVariant, string> = {
  default: "badge",
  success: "badge badge--success",
  warning: "badge badge--warning",
  failed: "badge badge--failed",
  running: "badge badge--running",
  unstyled: "",
};

export type BadgeProps = React.HTMLAttributes<HTMLSpanElement> &
  VariantProps<typeof badgeVariants> & {
    asChild?: boolean;
  };

export const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(function Badge(
  { className, variant, asChild = false, ...props },
  ref,
) {
  const Comp = asChild ? Slot : "span";
  const resolvedVariant = variant ?? "default";
  return (
    <Comp
      ref={ref}
      className={cn(badgeVariants({ variant: resolvedVariant }), legacyBadgeVariants[resolvedVariant], className)}
      data-ui-primitive={resolvedVariant === "unstyled" ? undefined : "badge"}
      data-ui-variant={resolvedVariant === "unstyled" ? undefined : resolvedVariant}
      {...props}
    />
  );
});
