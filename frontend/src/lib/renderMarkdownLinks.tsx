export function renderMarkdownLinks(text: string): React.ReactNode[] {
  // Match [anything](url) where anything can include escaped brackets \[ or \]
  const linkRegex = /\[((?:[^\\\[\]]|\\\[|\\\])*)\]\((https?:\/\/[^)]+)\)/g;
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = linkRegex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }

    const [, rawText, url] = match;
    // Remove escapes from link text: \[ → [, \] → ]
    const linkText = rawText.replace(/\\([\[\]])/g, "$1");

    parts.push(
      <a
        key={match.index}
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="text-primary hover:underline"
      >
        {linkText}
      </a>,
    );

    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts;
}
