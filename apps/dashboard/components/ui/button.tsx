import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

export type ButtonVariant = "default" | "secondary" | "ghost" | "destructive" | "warning" | "unstyled";

function cn(...parts: Array<string | undefined | null | false>): string {
  return parts.filter(Boolean).join(" ");
}

export const buttonVariants = cva("", {
  variants: {
    variant: {
      default: "ui-button ui-button--primary",
      secondary: "ui-button ui-button--secondary",
      ghost: "ui-button ui-button--ghost",
      destructive: "ui-button ui-button--destructive",
      warning: "ui-button ui-button--warning",
      unstyled: "",
    } satisfies Record<ButtonVariant, string>,
  },
  defaultVariants: {
    variant: "secondary",
  },
});

const legacyButtonVariants: Record<ButtonVariant, string> = {
  default: "btn btn-primary",
  secondary: "btn",
  ghost: "btn btn-ghost",
  destructive: "btn btn-danger",
  warning: "btn btn-warning",
  unstyled: "",
};

export type ButtonClassOptions = {
  variant?: ButtonVariant;
  className?: string;
};

export function buttonClasses(options?: ButtonClassOptions): string;
export function buttonClasses(variant?: ButtonVariant, className?: string): string;
export function buttonClasses(
  optionsOrVariant: ButtonClassOptions | ButtonVariant = "secondary",
  classNameArg?: string,
): string {
  const options =
    typeof optionsOrVariant === "string"
      ? { variant: optionsOrVariant, className: classNameArg }
      : optionsOrVariant;
  const variant = options?.variant ?? "secondary";
  const className = options?.className;
  return cn(buttonVariants({ variant }), legacyButtonVariants[variant], className);
}

export type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean;
  };

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant, asChild = false, ...props },
  ref,
) {
  const Comp = asChild ? Slot : "button";
  const resolvedVariant = variant ?? "secondary";
  const elementProps = !asChild && props.type === undefined ? { ...props, type: "button" as const } : props;
  return (
    <Comp
      ref={ref}
      className={buttonClasses(resolvedVariant, className)}
      data-ui-primitive={resolvedVariant === "unstyled" ? undefined : "button"}
      data-ui-variant={resolvedVariant === "unstyled" ? undefined : resolvedVariant}
      {...elementProps}
    />
  );
});
