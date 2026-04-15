type CapabilityGap = {
  capability: string;
  missingCapability: string;
  nextBestAction: string;
  approvalTitle: string;
  approvalBody: string;
  taskTitle: string;
  taskNotes: string;
  suggestionTitle: string;
  suggestionBody: string;
  reply: string;
  dedupeKey: string;
};

type CapabilityGapRule = {
  capability: string;
  pattern: RegExp;
  build: (message: string) => CapabilityGap;
};

function normalizeQuoted(message: string): string {
  return message.trim().replace(/\s+/g, " ");
}

const RULES: CapabilityGapRule[] = [
  {
    capability: "interface-control",
    pattern: /\b(click|tap|scroll|open that|close that|control the interface|control the ui|direct interface control|independent interface control|use the interface)\b/i,
    build(message) {
      return {
        capability: "interface-control",
        missingCapability: "direct interface control",
        nextBestAction: "Queue the interface-control bridge immediately and make it the next builder slice so ARI can stop treating interface control as an external dependency.",
        approvalTitle: "Queue interface-control bridge",
        approvalBody: "Missing capability: direct interface control. Approve and ARI will queue the implementation slice now.",
        taskTitle: "Implement interface-control bridge for ACE",
        taskNotes: `Capability gap detected from request: "${normalizeQuoted(message)}". Build the safe interface-control bridge now. The target is for ARI to control interface elements directly instead of handing this class of work back to Alec.`,
        suggestionTitle: "Queue interface-control bridge now",
        suggestionBody: "ARI identified a direct interface-control gap. The next best move is to queue the bridge immediately and make it the next implementation slice.",
        dedupeKey: "capability-gap:interface-control",
        reply:
          "Missing capability: direct interface control. I recommend queuing the interface-control bridge immediately so this stops blocking execution. I have prepared the approval to move that slice forward now."
      };
    }
  },
  {
    capability: "artifact-generation",
    pattern: /\b(generate|create|export|produce)\b.*\b(pdf|docx|document|artifact|report|image|deck|slide|slides)\b/i,
    build(message) {
      return {
        capability: "artifact-generation",
        missingCapability: "direct artifact generation pipeline",
        nextBestAction: "Prepare the content/spec now and queue the generation pipeline immediately so ARI can produce the requested artifact directly next time.",
        approvalTitle: "Queue artifact-generation pipeline",
        approvalBody: "Missing capability: direct artifact-generation pipeline. Approve and ARI will queue the implementation slice now.",
        taskTitle: "Add artifact-generation pipeline",
        taskNotes: `Capability gap detected from request: "${normalizeQuoted(message)}". Build the missing generation/export path now so ARI can produce the requested artifact directly instead of stopping at preparation only.`,
        suggestionTitle: "Queue artifact-generation pipeline now",
        suggestionBody: "ARI identified a direct artifact-generation gap. The right move is to queue the generation path immediately while preserving the requested output shape.",
        dedupeKey: "capability-gap:artifact-generation",
        reply:
          "Missing capability: direct artifact generation. I can still prepare the content, but the important move is to queue the generation pipeline now so this becomes executable instead of aspirational. I have prepared that approval."
      };
    }
  },
  {
    capability: "notification-delivery",
    pattern: /\b(push notification|browser notification|notify me|iphone notification|phone notification|alert me)\b/i,
    build(message) {
      return {
        capability: "notification-delivery",
        missingCapability: "notification delivery channel",
        nextBestAction: "Queue the notification delivery slice now so ARI can move important approvals and alerts beyond the hub.",
        approvalTitle: "Queue notification delivery channel",
        approvalBody: "Missing capability: notification delivery channel. Approve and ARI will queue the implementation slice now.",
        taskTitle: "Add notification delivery channel",
        taskNotes: `Capability gap detected from request: "${normalizeQuoted(message)}". Build browser/phone notification delivery now so ARI can surface approvals and important events directly instead of only inside the hub.`,
        suggestionTitle: "Queue notification delivery now",
        suggestionBody: "ARI identified a notification-delivery gap. The next best move is to queue the delivery channel immediately rather than leave the request trapped in the hub.",
        dedupeKey: "capability-gap:notification-delivery",
        reply:
          "Missing capability: notification delivery. I recommend queuing the delivery channel now so approvals and alerts can leave the hub cleanly. I have prepared that approval."
      };
    }
  }
];

export function detectCapabilityGap(message: string): CapabilityGap | null {
  const trimmed = message.trim();
  if (!trimmed) {
    return null;
  }

  for (const rule of RULES) {
    if (rule.pattern.test(trimmed)) {
      return rule.build(trimmed);
    }
  }

  return null;
}

export type { CapabilityGap };
