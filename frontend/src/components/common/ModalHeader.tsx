import { X, LucideIcon } from "lucide-react";

interface ModalHeaderProps {
  title: string;
  subtitle?: string;
  icon?: LucideIcon;
  iconColor?: string;
  onClose: () => void;
  disabled?: boolean;
}

export function ModalHeader({
  title,
  subtitle,
  icon: Icon,
  iconColor = "text-primary",
  onClose,
  disabled = false,
}: ModalHeaderProps) {
  return (
    <div className="flex items-center justify-between p-6 border-b border-border-light dark:border-border-dark">
      <div className="flex items-center gap-3">
        {Icon && (
          <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
            <Icon className={`w-5 h-5 ${iconColor}`} />
          </div>
        )}
        <div>
          <h2 className="text-lg font-semibold">{title}</h2>
          {subtitle && (
            <p className="text-sm text-gray-500 dark:text-gray-400 truncate max-w-md">
              {subtitle}
            </p>
          )}
        </div>
      </div>
      <button
        onClick={onClose}
        disabled={disabled}
        className="cursor-pointer p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-white/5 "
      >
        <X className="w-5 h-5" />
      </button>
    </div>
  );
}
