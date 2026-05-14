import { ArrowUpDown, ArrowDownAZ, LucideIcon } from "lucide-react";

export type SortOption =
  | "date_desc"
  | "date_asc"
  | "score_desc"
  | "score_asc"
  | "title_asc";

export interface SortOptionConfig {
  value: SortOption;
  label: string;
  icon: LucideIcon;
}

export const SORT_OPTIONS: SortOptionConfig[] = [
  { value: "date_desc", label: "Newest first", icon: ArrowUpDown },
  { value: "date_asc", label: "Oldest first", icon: ArrowUpDown },
  { value: "score_desc", label: "Upvotes: High → Low", icon: ArrowUpDown },
  { value: "score_asc", label: "Upvotes: Low → High", icon: ArrowUpDown },
  { value: "title_asc", label: "Alphabetical", icon: ArrowDownAZ },
];
