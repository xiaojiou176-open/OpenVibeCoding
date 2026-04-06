import { forwardRef, type InputHTMLAttributes, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";

function joinClasses(...parts: Array<string | undefined>) {
  return parts.filter(Boolean).join(" ").trim();
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input(
  { className, ...rest }: InputHTMLAttributes<HTMLInputElement>,
  ref,
) {
  const classes = joinClasses("ui-input", className);
  return <input ref={ref} className={classes} {...rest} />;
});

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select(
  { className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>,
  ref,
) {
  const classes = joinClasses("ui-input", className);
  return (
    <select ref={ref} className={classes} {...rest}>
      {children}
    </select>
  );
});

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea(
  { className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>,
  ref,
) {
  const classes = joinClasses("ui-input", className);
  return <textarea ref={ref} className={classes} {...rest} />;
});
