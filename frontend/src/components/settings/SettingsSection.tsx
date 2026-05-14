import { ReactNode } from "react";
import { LucideIcon } from "lucide-react";

interface SettingsSectionProps {
  title: string;
  icon: LucideIcon;
  children: ReactNode;
}

export function SettingsSection({
  title,
  icon: Icon,
  children,
}: SettingsSectionProps) {
  return (
    <div className="card p-6 mb-6">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
          <Icon className="w-5 h-5 text-primary" />
        </div>
        <h3 className="text-lg font-semibold">{title}</h3>
      </div>
      {children}
    </div>
  );
}
