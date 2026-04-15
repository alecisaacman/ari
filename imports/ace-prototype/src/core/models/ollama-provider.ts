import type { ModelProvider, SpeechResult, TextGenerationInput, TextGenerationResult, TranscriptionResult } from "@/src/core/models/provider";

export class OllamaProvider implements ModelProvider {
  mode: "hosted" = "hosted";
  supportsTranscription = false;
  supportsSpeechSynthesis = false;

  async generateText(_input: TextGenerationInput): Promise<TextGenerationResult> {
    throw new Error("Ollama support is scaffolded but not enabled in ARI v1.");
  }

  async transcribeAudio(_file: File): Promise<TranscriptionResult> {
    throw new Error("Ollama transcription is not enabled in ARI v1.");
  }

  async synthesizeSpeech(_text: string): Promise<SpeechResult> {
    throw new Error("Ollama speech synthesis is not enabled in ARI v1.");
  }
}
