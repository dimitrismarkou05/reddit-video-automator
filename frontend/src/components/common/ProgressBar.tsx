interface ProgressBarProps {
  progress: number;
  className?: string;
  barClassName?: string;
  showPercentage?: boolean;
  size?: "sm" | "md" | "lg";
}

const sizeMap = {
  sm: "h-1.5",
  md: "h-2.5",
  lg: "h-4",
};

export function ProgressBar({
  progress,
  className = "",
  barClassName = "",
  showPercentage = true,
  size = "md",
}: ProgressBarProps) {
  const clamped = Math.min(100, Math.max(0, progress));

  return (
    <div className={`w-full ${className}`}>
      <div
        className={`w-full bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden ${sizeMap[size]}`}
      >
        <div
          className={`h-full bg-primary rounded-full transition-all duration-300 ease-out ${barClassName}`}
          style={{ width: `${clamped}%` }}
        />
      </div>
      {showPercentage && (
        <div className="flex justify-between mt-1">
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {clamped}%
          </span>
        </div>
      )}
    </div>
  );
}
