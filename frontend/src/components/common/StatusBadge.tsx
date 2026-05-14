import { LucideIcon } from "lucide-react";

interface StatusBadgeProps {
  label: string;
  icon?: LucideIcon;
  variant?: "primary" | "success" | "warning" | "error" | "info" | "neutral";
  className?: string;
}

const variantStyles = {
  primary: "bg-primary/10 text-primary",
  success: "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400",
  warning: "bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400",
  error: "bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400",
  info: "bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400",
  neutral: "bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400",
};

export function StatusBadge({
  label,
  icon: Icon,
  variant = "neutral",
  className = "",
}: StatusBadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${variantStyles[variant]} ${className}`}
    >
      {Icon && <Icon className="w-3 h-3" />}
      {label}
    </span>
  );
}
