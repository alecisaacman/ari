import { classifyCanonicalBuilderOutput, type OrchestrationClassification } from "@/src/core/ari-spine/policy-bridge";

export function classifyBuilderOutput(
  rawOutput: string,
  context: {
    currentPriority?: string;
    latestDecision?: string;
  } = {}
): OrchestrationClassification {
  return classifyCanonicalBuilderOutput({
    rawOutput,
    currentPriority: context.currentPriority,
    latestDecision: context.latestDecision
  });
}

export type { OrchestrationClassification };

