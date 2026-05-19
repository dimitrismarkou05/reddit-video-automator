// store/theme.ts
import { create } from "zustand";
import { persist } from "zustand/middleware";

interface ThemeState {
  isDark: boolean;
  toggle: () => void;
  setDark: (dark: boolean) => void;
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      isDark: false,
      toggle: () => {
        if (typeof document !== "undefined" && document.startViewTransition) {
          // Add disable class before ViewTransition
          document.documentElement.classList.add("disable-transitions");

          // Force reflow
          void document.documentElement.offsetHeight;

          document
            .startViewTransition(() => {
              set((state) => ({ isDark: !state.isDark }));
            })
            .finished.finally(() => {
              // Remove disable class after transition completes
              document.documentElement.classList.remove("disable-transitions");
            });
        } else {
          // Fallback for older browsers
          document.documentElement.classList.add("disable-transitions");
          void document.documentElement.offsetHeight;
          set((state) => ({ isDark: !state.isDark }));
          requestAnimationFrame(() => {
            requestAnimationFrame(() => {
              document.documentElement.classList.remove("disable-transitions");
            });
          });
        }
      },
      setDark: (dark) => set({ isDark: dark }),
    }),
    {
      name: "rva-theme",
    },
  ),
);
