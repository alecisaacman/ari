import type { ModelProvider, SpeechResult, TextGenerationInput, TextGenerationResult, TranscriptionResult } from "@/src/core/models/provider";
import { buildDeterministicFallbackReply } from "@/src/core/identity";

export class DeterministicFallbackProvider implements ModelProvider {
  mode: "fallback" = "fallback";
  supportsTranscription = false;
  supportsSpeechSynthesis = false;

  async generateText(input: TextGenerationInput): Promise<TextGenerationResult> {
    const lastUserMessage = [...input.messages].reverse().find((message) => message.role === "user")?.content || "";
    return {
      mode: this.mode,
      text: buildDeterministicFallbackReply(lastUserMessage, 0)
    };
  }

  async transcribeAudio(_file: File): Promise<TranscriptionResult> {
    throw new Error("Hosted transcription is not configured.");
  }

  async synthesizeSpeech(_text: string): Promise<SpeechResult> {
    throw new Error("Hosted speech synthesis is not configured.");
  }
}
