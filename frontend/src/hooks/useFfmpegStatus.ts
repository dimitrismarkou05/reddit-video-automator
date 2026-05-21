import { useQuery, useMutation } from "@tanstack/react-query";
import { ffmpegApi } from "@/services/api";
import { useFfmpegStore } from "@/store/ffmpeg";

export function useFfmpegStatus() {
  const { status, setStatus, setChecking } = useFfmpegStore();

  const { data, refetch, isLoading } = useQuery({
    queryKey: ["ffmpeg-status"],
    queryFn: async () => {
      setChecking(true);
      try {
        const { data } = await ffmpegApi.getStatus();
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

export function useFfmpegInstall() {
  const { startInstall, failInstall } = useFfmpegStore();

  const installMutation = useMutation({
    mutationFn: async () => {
      startInstall();
      const { data } = await ffmpegApi.install();
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

export function useFfmpegCancel() {
  const { resetInstall } = useFfmpegStore();

  return useMutation({
    mutationFn: async () => {
      const { data } = await ffmpegApi.cancel();
      return data;
    },
    onSuccess: () => {
      resetInstall();
    },
  });
}
