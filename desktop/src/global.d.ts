export {};

declare global {
  interface Window {
    ycAgentsDesktop?: {
      version: string;
      apiBaseUrl?: string;
      wsBaseUrl?: string;
      selectProjectDirectory(): Promise<string | null>;
    };
  }
}
