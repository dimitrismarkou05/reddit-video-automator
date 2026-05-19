import { X } from "lucide-react";

interface SubredditBadgeProps {
  sub: { id: number; display_name: string };
  onDelete: (id: number, name: string) => void;
}

export function SubredditBadge({ sub, onDelete }: SubredditBadgeProps) {
  return (
    <span className="group inline-flex items-center gap-1.5 px-3 py-1.5 bg-primary/10 text-primary text-sm rounded-full font-medium  hover:bg-primary/15">
      {sub.display_name}
      <button
        onClick={(e) => {
          e.stopPropagation();
          onDelete(sub.id, sub.display_name);
        }}
        className="cursor-pointer flex items-center justify-center w-5 h-5 rounded-full text-primary  hover:bg-primary/20 hover:text-primary-foreground"
        title={`Remove ${sub.display_name}`}
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </span>
  );
}
