// frontend/src/components/common/ConfirmDialog.tsx
import { AlertTriangle, Loader2, Trash2, X } from "lucide-react";
import { ModalShell } from "./ModalShell";

interface ConfirmDialogProps {
  title: string;
  message: string;
  warning?: string;
  confirmLabel?: string;
  dismissLabel?: string;
  confirmIcon?: React.ReactNode;
  onConfirm: () => void;
  onCancel: () => void;
  isDanger?: boolean;
  isConfirming?: boolean;
  overlayClassName?: string;
}

export function ConfirmDialog({
  title,
  message,
  warning,
  confirmLabel = "Delete",
  dismissLabel = "Cancel",
  confirmIcon,
  onConfirm,
  onCancel,
  isDanger = true,
  isConfirming = false,
  overlayClassName,
}: ConfirmDialogProps) {
  return (
    <ModalShell onClose={onCancel} maxWidth="max-w-md" overlayClassName={overlayClassName}>
      <div className="p-6 relative">
        <button
          onClick={onCancel}
          disabled={isConfirming}
          className="cursor-pointer absolute top-4 right-4 p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-white/5 z-10 disabled:opacity-50"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-3 mb-4">
          <div
            className={`w-10 h-10 rounded-xl flex items-center justify-center ${
              isDanger
                ? "bg-red-100 dark:bg-red-900/30"
                : "bg-blue-100 dark:bg-blue-900/30"
            }`}
          >
            {isDanger ? (
              <AlertTriangle className="w-5 h-5 text-red-500" />
            ) : (
              <AlertTriangle className="w-5 h-5 text-blue-500" />
            )}
          </div>
          <h3 className="text-lg font-semibold">{title}</h3>
        </div>
        <p className="text-sm text-gray-600 dark:text-gray-300 mb-2">
          {message}
        </p>
        {warning && (
          <p className="text-sm text-red-600 dark:text-red-400 mb-4 bg-red-50 dark:bg-red-900/20 p-3 rounded-lg">
            {warning}
          </p>
        )}
        <div className="flex items-center justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={isConfirming}
            className="cursor-pointer btn-secondary disabled:opacity-50"
          >
            {dismissLabel}
          </button>
          <button
            onClick={onConfirm}
            disabled={isConfirming}
            className={`cursor-pointer px-4 py-2 rounded-lg font-medium flex items-center gap-2 disabled:opacity-50 ${
              isDanger
                ? "bg-red-500 text-white hover:bg-red-600"
                : "btn-primary"
            }`}
          >
            {isConfirming ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              confirmIcon || <Trash2 className="w-4 h-4" />
            )}
            {confirmLabel}
          </button>
        </div>
      </div>
    </ModalShell>
  );
}
