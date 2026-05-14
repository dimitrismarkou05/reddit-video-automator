import { ArrowUp, MessageCircle, Calendar } from "lucide-react";
import { formatUtcRelative } from "@/lib/formatters";
import type { Story } from "@/types";

interface StoryMetaProps {
  story: Story;
}

export function StoryMeta({ story }: StoryMetaProps) {
  return (
    <div className="flex items-center gap-4 text-sm text-gray-500 dark:text-gray-400 flex-wrap">
      <span className="flex items-center gap-1">
        <ArrowUp className="w-3 h-3" />
        {story.score.toLocaleString()}
      </span>
      <span className="flex items-center gap-1">
        <MessageCircle className="w-3 h-3" />
        u/{story.author}
      </span>
      <span className="flex items-center gap-1">
        <Calendar className="w-3 h-3" />
        {formatUtcRelative(story.created_utc)}
      </span>
    </div>
  );
}
