import { useQuery } from "@tanstack/react-query";
import { ttsLocalApi } from "@/services/api";

export function useTtsLocalStatus() {
  return useQuery({
    queryKey: ["tts-local-status"],
    queryFn: async () => {
      const { data } = await ttsLocalApi.getStatus();
      return data;
    },
    staleTime: 60000,
  });
}
