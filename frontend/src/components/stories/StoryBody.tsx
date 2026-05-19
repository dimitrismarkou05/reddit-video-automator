import { renderMarkdownLinks } from "@/lib/renderMarkdownLinks";

interface StoryBodyProps {
  body: string | null;
}

export function StoryBody({ body }: StoryBodyProps) {
  if (!body) return null;
  return (
    <p className="mt-2 text-sm text-gray-600 dark:text-gray-300 line-clamp-2">
      {renderMarkdownLinks(body)}
    </p>
  );
}
