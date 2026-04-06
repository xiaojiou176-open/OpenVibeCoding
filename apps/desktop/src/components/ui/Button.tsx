import { forwardRef, type ButtonHTMLAttributes, type PropsWithChildren } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost" | "destructive" | "icon" | "unstyled";

type ButtonProps = PropsWithChildren<
  ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: ButtonVariant;
    fullWidth?: boolean;
    unstyled?: boolean;
  }
>;

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "secondary",
    fullWidth = false,
    unstyled = false,
    className,
    children,
    ...rest
  }: ButtonProps,
  ref,
) {
  const isUnstyled = variant === "unstyled" || unstyled;
  const classes = isUnstyled
    ? [fullWidth ? "is-full" : "", className ?? ""].join(" ").trim()
    : ["ui-button", `ui-button-${variant}`, fullWidth ? "is-full" : "", className ?? ""].join(" ").trim();

  return (
    <button ref={ref} type="button" className={classes} {...rest}>
      {children}
    </button>
  );
});
