import type { HTMLAttributes, PropsWithChildren } from "react";

type CardProps = PropsWithChildren<HTMLAttributes<HTMLDivElement>>;
type CardTitleProps = PropsWithChildren<HTMLAttributes<HTMLHeadingElement>>;

function joinClasses(...parts: Array<string | undefined>) {
  return parts.filter(Boolean).join(" ").trim();
}

export function Card({ className, children, ...rest }: CardProps) {
  const classes = joinClasses("ui-card", className);
  return (
    <div className={classes} {...rest}>
      {children}
    </div>
  );
}

export function CardHeader({ className, children, ...rest }: CardProps) {
  const classes = joinClasses("ui-card-header", className);
  return (
    <div className={classes} {...rest}>
      {children}
    </div>
  );
}

export function CardTitle({ className, children, ...rest }: CardTitleProps) {
  const classes = joinClasses("ui-card-title", className);
  return (
    <h3 className={classes} {...rest}>
      {children}
    </h3>
  );
}

export function CardBody({ className, children, ...rest }: CardProps) {
  const classes = joinClasses("ui-card-body", className);
  return (
    <div className={classes} {...rest}>
      {children}
    </div>
  );
}
