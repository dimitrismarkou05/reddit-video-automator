import { Trash2 } from "lucide-react";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";

interface DeleteConfirmModalProps {
  title: string;
  message: string;
  warning?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function DeleteConfirmModal({
  title,
  message,
  warning,
  onConfirm,
  onCancel,
}: DeleteConfirmModalProps) {
  return (
    <ConfirmDialog
      title={title}
      message={message}
      warning={warning}
      confirmLabel="Delete"
      confirmIcon={<Trash2 className="w-4 h-4" />}
      onConfirm={onConfirm}
      onCancel={onCancel}
      isDanger
    />
  );
}
