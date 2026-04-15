export type ChatMessage = {
  role: "system" | "user" | "assistant";
  content: string;
};

export type TextGenerationInput = {
  systemPrompt: string;
  messages: ChatMessage[];
};

export type TextGenerationResult = {
  text: string;
  mode: "hosted" | "fallback";
};

export type TranscriptionResult = {
  transcript: string;
  mode: "hosted" | "fallback";
};

export type SpeechResult = {
  audioBuffer: ArrayBuffer;
  contentType: string;
  mode: "hosted" | "fallback";
};

export interface ModelProvider {
  mode: "hosted" | "fallback";
  supportsTranscription: boolean;
  supportsSpeechSynthesis: boolean;
  generateText(input: TextGenerationInput): Promise<TextGenerationResult>;
  transcribeAudio(file: File): Promise<TranscriptionResult>;
  synthesizeSpeech(text: string): Promise<SpeechResult>;
}
