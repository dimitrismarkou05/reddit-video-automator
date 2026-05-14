interface StoryBodyProps {
  body: string | null;
}

export function StoryBody({ body }: StoryBodyProps) {
  if (!body) return null;
  return (
    <p className="mt-2 text-sm text-gray-600 dark:text-gray-300 line-clamp-2">
      {body.substring(0, 200)}
      {body.length > 200 ? "..." : ""}
    </p>
  );
}
