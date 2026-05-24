import { useQuery, useMutation } from "@tanstack/react-query";
import { ttsLocalApi } from "@/services/api";
import { useTtsStore } from "@/store/tts";

export function useTtsLocalStatus() {
  const { status, setStatus, setChecking } = useTtsStore();

  const { data, refetch, isLoading } = useQuery({
    queryKey: ["tts-local-status"],
    queryFn: async () => {
      setChecking(true);
      try {
        const { data } = await ttsLocalApi.getStatus();
        setStatus(data);
        return data;
      } finally {
        setChecking(false);
      }
    },
    refetchInterval: 30000,
    staleTime: 10000,
  });

  return { status: data ?? status, refetch, isLoading };
}

export function useTtsInstall() {
  const { startInstall, failInstall } = useTtsStore();

  const installMutation = useMutation({
    mutationFn: async () => {
      startInstall();
      const { data } = await ttsLocalApi.install();
      return data;
    },
    onError: (error: any) => {
      failInstall(
        error?.response?.data?.detail || "Installation request failed",
      );
    },
  });

  return { installMutation };
}

export function useTtsCancel() {
  const { resetInstall } = useTtsStore();

  return useMutation({
    mutationFn: async () => {
      const { data } = await ttsLocalApi.cancel();
      return data;
    },
    onSuccess: () => {
      resetInstall();
    },
  });
}
