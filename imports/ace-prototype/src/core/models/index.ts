import { resolveMode } from "@/src/core/config";
import { DeterministicFallbackProvider } from "@/src/core/models/fallback-provider";
import { HostedModelProvider } from "@/src/core/models/hosted-provider";
import type { ModelProvider } from "@/src/core/models/provider";

let providerInstance: ModelProvider | null = null;

export function getModelProvider(): ModelProvider {
  if (providerInstance) {
    return providerInstance;
  }

  providerInstance = resolveMode() === "hosted" ? new HostedModelProvider() : new DeterministicFallbackProvider();
  return providerInstance;
}

export function resetModelProvider(): void {
  providerInstance = null;
}
