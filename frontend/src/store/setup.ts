import { create } from "zustand";
import { persist } from "zustand/middleware";

interface SetupState {
  wizardComplete: boolean;
  setWizardComplete: (complete: boolean) => void;
  resetWizard: () => void;
}

export const useSetupStore = create<SetupState>()(
  persist(
    (set) => ({
      wizardComplete: false,
      setWizardComplete: (complete) => set({ wizardComplete: complete }),
      resetWizard: () => set({ wizardComplete: false }),
    }),
    {
      name: "rva-setup-wizard",
    },
  ),
);
