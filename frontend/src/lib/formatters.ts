import { parseISO, formatDistanceToNow } from "date-fns";

export function formatUtcRelative(dateString: string | null): string {
  if (!dateString) return "Unknown";
  try {
    const date = parseISO(dateString);
    return formatDistanceToNow(date, { addSuffix: true });
  } catch {
    return "Unknown";
  }
}

export function stripUpdatePrefix(title: string): string {
  return title.replace(/^Update\s*(?:\d+)?\s*:\s*/i, "").trim();
}
