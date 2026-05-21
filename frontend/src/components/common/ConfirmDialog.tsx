// frontend/src/components/common/ConfirmDialog.tsx
import { AlertTriangle, Trash2, X } from "lucide-react"; // Add X
import { ModalShell } from "./ModalShell";

interface ConfirmDialogProps {
  title: string;
  message: string;
  warning?: string;
  confirmLabel?: string;
  confirmIcon?: React.ReactNode;
  onConfirm: () => void;
  onCancel: () => void;
  isDanger?: boolean;
}

export function ConfirmDialog({
  title,
  message,
  warning,
  confirmLabel = "Delete",
  confirmIcon,
  onConfirm,
  onCancel,
  isDanger = true,
}: ConfirmDialogProps) {
  return (
    <ModalShell onClose={onCancel} maxWidth="max-w-md">
      <div className="p-6 relative">
        <button
          onClick={onCancel}
          className="cursor-pointer absolute top-4 right-4 p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-white/5 z-10"
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
          <button onClick={onCancel} className="cursor-pointer btn-secondary">
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className={`cursor-pointer px-4 py-2 rounded-lg font-medium flex items-center gap-2 ${
              isDanger
                ? "bg-red-500 text-white hover:bg-red-600"
                : "btn-primary"
            }`}
          >
            {confirmIcon || <Trash2 className="w-4 h-4" />}
            {confirmLabel}
          </button>
        </div>
      </div>
    </ModalShell>
  );
}
