import type { HTMLAttributes, PropsWithChildren } from "react";

type BadgeVariant = "default" | "success" | "warning" | "failed" | "danger" | "info" | "muted" | "running";

type BadgeProps = PropsWithChildren<
  HTMLAttributes<HTMLSpanElement> & {
    variant?: BadgeVariant;
  }
>;

const variantClassMap: Record<Exclude<BadgeVariant, "default">, string> = {
  success: "ui-badge--success",
  warning: "ui-badge--warning",
  failed: "ui-badge--failed",
  danger: "ui-badge--danger",
  info: "ui-badge--info",
  muted: "ui-badge--muted",
  running: "ui-badge--running",
};

function joinClasses(...parts: Array<string | undefined>) {
  return parts.filter(Boolean).join(" ").trim();
}

export function Badge({ variant = "default", className, children, ...rest }: BadgeProps) {
  const hasLegacyBadgeClass = /\bbadge(?:--[\w-]+)?\b/.test(className ?? "");
  const hasUiBadgeClass = /\bui-badge(?:--[\w-]+)?\b/.test(className ?? "");
  const variantClass = variant === "default" ? "" : variantClassMap[variant];
  const classes = hasLegacyBadgeClass || hasUiBadgeClass
    ? joinClasses(className ?? "")
    : joinClasses("ui-badge", variantClass, className);

  return (
    <span className={classes} {...rest}>
      {children}
    </span>
  );
}
