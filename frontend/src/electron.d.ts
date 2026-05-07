export {};

declare global {
  interface Window {
    electronAPI: {
      openExternal: (url: string) => Promise<void>;
      selectDirectory: () => Promise<string | null>;
      selectFile: (filters?: Array<{ name: string; extensions: string[] }>) => Promise<string | null>;
      platform: string;
    };
  }
}
