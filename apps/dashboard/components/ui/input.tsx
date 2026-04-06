import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

export type InputVariant = "default" | "unstyled";

function cn(...parts: Array<string | undefined | null | false>): string {
  return parts.filter(Boolean).join(" ");
}

export const inputVariants = cva("", {
  variants: {
    variant: {
      default: "ui-input",
      unstyled: "",
    } satisfies Record<InputVariant, string>,
  },
  defaultVariants: {
    variant: "default",
  },
});

const legacyInputVariants: Record<InputVariant, string> = {
  default: "input",
  unstyled: "",
};

export type InputProps = React.InputHTMLAttributes<HTMLInputElement> & VariantProps<typeof inputVariants>;
export type SelectProps = React.SelectHTMLAttributes<HTMLSelectElement> & VariantProps<typeof inputVariants>;
export type TextareaProps = React.TextareaHTMLAttributes<HTMLTextAreaElement> &
  VariantProps<typeof inputVariants>;

export const Input = React.forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, variant, ...props },
  ref,
) {
  const resolvedVariant = variant ?? "default";
  return (
    <input
      ref={ref}
      className={cn(inputVariants({ variant: resolvedVariant }), legacyInputVariants[resolvedVariant], className)}
      data-ui-primitive={resolvedVariant === "unstyled" ? undefined : "input"}
      data-ui-variant={resolvedVariant === "unstyled" ? undefined : resolvedVariant}
      {...props}
    />
  );
});

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { className, variant, children, ...props },
  ref,
) {
  const resolvedVariant = variant ?? "default";
  return (
    <select
      ref={ref}
      className={cn(inputVariants({ variant: resolvedVariant }), legacyInputVariants[resolvedVariant], className)}
      data-ui-primitive={resolvedVariant === "unstyled" ? undefined : "select"}
      data-ui-variant={resolvedVariant === "unstyled" ? undefined : resolvedVariant}
      {...props}
    >
      {children}
    </select>
  );
});

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { className, variant, ...props },
  ref,
) {
  const resolvedVariant = variant ?? "default";
  return (
    <textarea
      ref={ref}
      className={cn(
        inputVariants({ variant: resolvedVariant }),
        legacyInputVariants[resolvedVariant],
        resolvedVariant === "unstyled" ? undefined : "ui-textarea",
        className,
      )}
      data-ui-primitive={resolvedVariant === "unstyled" ? undefined : "textarea"}
      data-ui-variant={resolvedVariant === "unstyled" ? undefined : resolvedVariant}
      {...props}
    />
  );
});
