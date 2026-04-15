import { getModelProvider } from "@/src/core/models";

export function getVoiceCapabilities() {
  const provider = getModelProvider();
  return {
    serverTranscription: provider.supportsTranscription,
    serverSpeechSynthesis: provider.supportsSpeechSynthesis,
    browserFallbackInput: true,
    browserFallbackOutput: true
  };
}
