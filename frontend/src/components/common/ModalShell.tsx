// frontend/src/components/common/ModalShell.tsx
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
  maxWidth = "max-w-md",
  maxHeight = "max-h-[90vh]",
}: ModalShellProps) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div
        className={`bg-surface-light dark:bg-surface-dark rounded-2xl w-full ${maxWidth} ${maxHeight} overflow-y-auto shadow-xl relative`}
      >
        {children}
      </div>
    </div>
  );
}
