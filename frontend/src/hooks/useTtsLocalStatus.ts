import { useQuery } from "@tanstack/react-query";
import { ttsLocalApi } from "@/services/api";
import { useState } from "react";

export function useTtsLocalStatus() {
  const [localStatus, setLocalStatus] = useState(null);

  const { data, refetch, isLoading } = useQuery({
    queryKey: ["tts-local-status"],
    queryFn: async () => {
      const { data } = await ttsLocalApi.getStatus();
      setLocalStatus(data);
      return data;
    },
    refetchInterval: 30000,
    staleTime: 10000,
  });

  return { status: data ?? localStatus, refetch, isLoading };
}
