interface StoryPaginationProps {
  currentPage: number;
  totalPages: number;
  showingStart: number;
  showingEnd: number;
  totalStories: number;
  onPageChange: (page: number) => void;
}

export function StoryPagination({
  currentPage,
  totalPages,
  showingStart,
  showingEnd,
  totalStories,
  onPageChange,
}: StoryPaginationProps) {
  if (totalStories === 0) return null;

  return (
    <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-4 border-t border-border-light dark:border-border-dark">
      <p className="text-sm text-gray-500 dark:text-gray-400">
        Showing{" "}
        <span className="font-medium text-gray-700 dark:text-gray-300">
          {showingStart}-{showingEnd}
        </span>{" "}
        of{" "}
        <span className="font-medium text-gray-700 dark:text-gray-300">
          {totalStories}
        </span>{" "}
        stories
      </p>
      <div className="flex items-center gap-2">
        <button
          onClick={() => onPageChange(Math.max(1, currentPage - 1))}
          disabled={currentPage === 1}
          className="cursor-pointer px-3 py-1.5 rounded-lg border border-border-light dark:border-border-dark text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
        >
          Previous
        </button>
        <span className="text-sm font-medium px-2">
          Page {currentPage} of {totalPages}
        </span>
        <button
          onClick={() => onPageChange(Math.min(totalPages, currentPage + 1))}
          disabled={currentPage === totalPages}
          className="cursor-pointer px-3 py-1.5 rounded-lg border border-border-light dark:border-border-dark text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
        >
          Next
        </button>
      </div>
    </div>
  );
}
