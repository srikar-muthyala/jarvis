export type JarvisMood = "online" | "listening" | "thinking" | "speaking" | "approval";

export interface TelemetryData {
  cpu: number;
  ram: number;
  bat: string;
  batLevel: number;
  charging: boolean;
}

export interface JarvisState {
  connected: boolean;
  expanded: boolean;
  statusLabel: string;
  statusColor: string;
  mood: JarvisMood;
  lastQuery: string;
  lastReply: string;
  isListening: boolean;
  isThinking: boolean;
  isSpeaking: boolean;
  hasApproval: boolean;
  approvalPrompt?: string;
  telemetry: TelemetryData;
}
