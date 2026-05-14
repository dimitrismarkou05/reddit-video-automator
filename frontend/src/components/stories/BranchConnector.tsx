interface BranchConnectorProps {
  index: number;
  total: number;
}

export function BranchConnector({ index, total }: BranchConnectorProps) {
  const isLast = index === total - 1;

  return (
    <div
      className="relative flex flex-col items-start"
      style={{ width: "36px", minWidth: "36px" }}
    >
      <div
        className="absolute w-0.5 bg-gray-400 dark:bg-gray-500"
        style={{
          left: "11px",
          height: index === 0 ? "82px" : "70px",
          top: index === 0 ? "-12px" : "0",
        }}
      />
      <div
        className="relative w-full"
        style={{ height: "20px", marginTop: "68px" }}
      >
        <svg
          className="absolute"
          style={{ left: "11px", top: "0px", width: "24px", height: "16px" }}
          viewBox="0 0 24 16"
          fill="none"
        >
          <path
            d="M 1 0 L 1 4 C 1 8, 4 10, 8 10 L 24 10"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            className="text-gray-400 dark:text-gray-500"
          />
        </svg>
      </div>
      {!isLast && (
        <div
          className="w-0.5 flex-1 bg-gray-400 dark:bg-gray-500"
          style={{ marginLeft: "11px", marginTop: "2px" }}
        />
      )}
    </div>
  );
}
