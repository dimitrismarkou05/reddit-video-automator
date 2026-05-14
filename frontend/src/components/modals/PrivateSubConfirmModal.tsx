import { ConfirmDialog } from "@/components/common/ConfirmDialog";

interface PrivateSubConfirmModalProps {
  name: string;
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function PrivateSubConfirmModal({
  name,
  message,
  onConfirm,
  onCancel,
}: PrivateSubConfirmModalProps) {
  return (
    <ConfirmDialog
      title={`Private Subreddit: ${name}`}
      message={message}
      confirmLabel="Add Anyway"
      onConfirm={onConfirm}
      onCancel={onCancel}
      isDanger={false}
    />
  );
}
