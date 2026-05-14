import { X } from "lucide-react";
import { ReactNode } from "react";

interface ModalShellProps {
  children: ReactNode;
  onClose: () => void;
  maxWidth?: string;
  maxHeight?: string;
  disabled?: boolean;
}

export function ModalShell({
  children,
  onClose,
  maxWidth = "max-w-md",
  maxHeight = "max-h-[90vh]",
  disabled = false,
}: ModalShellProps) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div
        className={`bg-surface-light dark:bg-surface-dark rounded-2xl w-full ${maxWidth} ${maxHeight} overflow-y-auto shadow-xl`}
      >
        <button
          onClick={onClose}
          disabled={disabled}
          className="cursor-pointer absolute top-4 right-4 p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors z-10"
        >
          <X className="w-5 h-5" />
        </button>
        {children}
      </div>
    </div>
  );
}
