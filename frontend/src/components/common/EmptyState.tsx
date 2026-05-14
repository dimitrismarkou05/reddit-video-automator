import { LucideIcon } from "lucide-react";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  subtitle?: string;
}

export function EmptyState({ icon: Icon, title, subtitle }: EmptyStateProps) {
  return (
    <div className="card p-12 text-center">
      <Icon className="w-12 h-12 mx-auto mb-4 text-gray-300" />
      <h3 className="text-lg font-semibold text-gray-500">{title}</h3>
      {subtitle && (
        <p className="text-sm text-gray-400 mt-1">{subtitle}</p>
      )}
    </div>
  );
}
