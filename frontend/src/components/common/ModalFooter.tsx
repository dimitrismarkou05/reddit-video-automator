import { ReactNode } from "react";

interface ModalFooterProps {
  children: ReactNode;
}

export function ModalFooter({ children }: ModalFooterProps) {
  return (
    <div className="flex items-center justify-end gap-3 p-6 border-t border-border-light dark:border-border-dark">
      {children}
    </div>
  );
}
