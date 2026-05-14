import { ReactNode } from "react";

interface FormFieldProps {
  label: string;
  children: ReactNode;
  hint?: string;
  error?: string;
}

export function FormField({ label, children, hint, error }: FormFieldProps) {
  return (
    <div className="space-y-1.5">
      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
        {label}
      </label>
      {children}
      {hint && <p className="text-xs text-gray-500">{hint}</p>}
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  );
}
