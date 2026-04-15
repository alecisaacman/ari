import { getConfig } from "@/src/core/config";
import type { ModelProvider, SpeechResult, TextGenerationInput, TextGenerationResult, TranscriptionResult } from "@/src/core/models/provider";

async function fetchJson(url: string, init: RequestInit): Promise<any> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Hosted provider request failed (${response.status}): ${body}`);
  }
  return response.json();
}

export class HostedModelProvider implements ModelProvider {
  mode: "hosted" = "hosted";
  supportsTranscription = true;
  supportsSpeechSynthesis = true;

  async generateText(input: TextGenerationInput): Promise<TextGenerationResult> {
    const config = getConfig();
    const payload = {
      model: config.openAiModel,
      messages: [
        { role: "system", content: input.systemPrompt },
        ...input.messages.map((message) => ({ role: message.role, content: message.content }))
      ]
    };

    const json = await fetchJson(`${config.openAiBaseUrl}/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${config.openAiApiKey}`
      },
      body: JSON.stringify(payload)
    });

    return {
      mode: this.mode,
      text: json.choices?.[0]?.message?.content || "ARI did not receive a hosted response."
    };
  }

  async transcribeAudio(file: File): Promise<TranscriptionResult> {
    const config = getConfig();
    const formData = new FormData();
    formData.append("file", file);
    formData.append("model", config.openAiTranscriptionModel);

    const response = await fetch(`${config.openAiBaseUrl}/audio/transcriptions`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${config.openAiApiKey}`
      },
      body: formData
    });

    if (!response.ok) {
      const body = await response.text();
      throw new Error(`Hosted transcription failed (${response.status}): ${body}`);
    }

    const json = await response.json();
    return {
      mode: this.mode,
      transcript: json.text || ""
    };
  }

  async synthesizeSpeech(text: string): Promise<SpeechResult> {
    const config = getConfig();
    const response = await fetch(`${config.openAiBaseUrl}/audio/speech`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${config.openAiApiKey}`
      },
      body: JSON.stringify({
        model: config.openAiTtsModel,
        voice: config.openAiTtsVoice,
        input: text
      })
    });

    if (!response.ok) {
      const body = await response.text();
      throw new Error(`Hosted speech synthesis failed (${response.status}): ${body}`);
    }

    return {
      mode: this.mode,
      audioBuffer: await response.arrayBuffer(),
      contentType: response.headers.get("content-type") || "audio/mpeg"
    };
  }
}
