import { X } from "lucide-react";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";

interface CancelConfirmModalProps {
  videoTitle: string;
  onConfirm: () => void;
  onCancel: () => void;
  isConfirming?: boolean;
}

export function CancelConfirmModal({
  videoTitle,
  onConfirm,
  onCancel,
  isConfirming = false,
}: CancelConfirmModalProps) {
  return (
    <ConfirmDialog
      title="Cancel Generation?"
      message={`Are you sure you want to cancel generation for "${videoTitle}"?`}
      warning="All progress on this video will be lost."
      confirmLabel="Yes"
      dismissLabel="No"
      confirmIcon={<X className="w-4 h-4" />}
      onConfirm={onConfirm}
      onCancel={onCancel}
      isDanger
      isConfirming={isConfirming}
      overlayClassName="z-[60]"
    />
  );
}
