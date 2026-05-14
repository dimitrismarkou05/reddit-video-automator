import { useState } from "react";
import type { Story } from "@/types";

export type DeleteTarget =
  | { type: "single"; id?: number; name?: string }
  | { type: "all" }
  | { type: "story"; story: Story }
  | { type: "all_stories" }
  | null;

export function useDeleteTarget() {
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget>(null);

  const clearTarget = () => setDeleteTarget(null);
  const setSingle = (id: number, name: string) =>
    setDeleteTarget({ type: "single", id, name });
  const setAll = () => setDeleteTarget({ type: "all" });
  const setStory = (story: Story) => setDeleteTarget({ type: "story", story });
  const setAllStories = () => setDeleteTarget({ type: "all_stories" });

  return {
    deleteTarget,
    setDeleteTarget,
    clearTarget,
    setSingle,
    setAll,
    setStory,
    setAllStories,
  };
}
