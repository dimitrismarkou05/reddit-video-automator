// frontend/src/components/common/ModalShell.tsx
import { ReactNode } from "react";

interface ModalShellProps {
  children: ReactNode;
  onClose: () => void;
  maxWidth?: string;
  maxHeight?: string;
  disabled?: boolean;
  overlayClassName?: string;
}

export function ModalShell({
  children,
  maxWidth = "max-w-md",
  maxHeight = "max-h-[90vh]",
  overlayClassName = "z-50",
}: ModalShellProps) {
  return (
    <div
      className={`fixed inset-0 bg-black/50 flex items-center justify-center p-4 ${overlayClassName}`}
    >
      <div
        className={`bg-surface-light dark:bg-surface-dark rounded-2xl w-full ${maxWidth} ${maxHeight} overflow-y-auto shadow-xl relative`}
      >
        {children}
      </div>
    </div>
  );
}
