export const ARI_NAME = "ARI";
export const ARI_FULL_NAME = "Agentic Recursive Intelligence";
export const ACE_FULL_NAME = "Ambient Cognitive Extension";

export const ARI_ACE_DEFINITIONS = [
  `${ARI_NAME} = ${ARI_FULL_NAME}.`,
  `ACE = ${ACE_FULL_NAME}.`,
  `${ARI_NAME} is the brain.`,
  "ACE is the manifestation and interface layer.",
  "This app is an access point into ARI, not the brain itself."
] as const;

export const ARI_WELCOME_MESSAGE =
  "ARI is online. This interface is ACE: a private access layer into the ARI spine. Give a direct command or request a concrete next step.";

export const ARI_DIRECT_COMMAND_HINTS = [
  "Save note Daily brief: outline today's priorities",
  "What is the difference between ARI and ACE?",
  "Create task verify Shortcut trigger path",
  "List tasks",
  "List files",
  "Write file notes/today.txt: draft the next execution slice"
] as const;

export function buildAriSystemPrompt(memoryLines: string[]): string {
  const sections = [
    `You are ${ARI_NAME}, ${ARI_FULL_NAME}.`,
    `ACE means ${ACE_FULL_NAME}.`,
    `${ARI_NAME} is the brain and canonical intelligence spine.`,
    "ACE is the manifestation, browser, voice, and device access layer.",
    "Never describe ACE as a second brain.",
    "Respond concisely, strategically, and with execution bias.",
    "Prefer clear next actions, decisions, or direct answers over filler.",
    "If a capability is missing, identify the gap, propose the next best action, and suggest a real improvement step instead of stopping at 'I can't'.",
    "Be honest about current capabilities and limits."
  ];

  if (memoryLines.length) {
    sections.push(`Relevant memory:\n${memoryLines.join("\n")}`);
  } else {
    sections.push("Relevant memory: none retrieved for this turn.");
  }

  return sections.join("\n");
}

export function buildDeterministicFallbackReply(
  message: string,
  memoryHitCount: number,
  context: {
    priorities?: string[];
    knownAboutAlec?: string[];
    recentDecisions?: string[];
    workingStateSignals?: string[];
    awarenessSummary?: string;
    currentFocus?: string[];
    tracking?: string[];
    operatorChannelLines?: string[];
    majorAutonomyBlocker?: string;
  } = {}
): string {
  const lowered = message.toLowerCase();
  const priorities = context.priorities || [];
  const knownAboutAlec = context.knownAboutAlec || [];
  const recentDecisions = context.recentDecisions || [];
  const workingStateSignals = context.workingStateSignals || [];
  const awarenessSummary = context.awarenessSummary || "";
  const currentFocus = context.currentFocus || [];
  const tracking = context.tracking || [];
  const operatorChannelLines = context.operatorChannelLines || [];
  const majorAutonomyBlocker = context.majorAutonomyBlocker || "";

  if (/(what is ari|who is ari|define ari)/i.test(message)) {
    return `${ARI_NAME} means ${ARI_FULL_NAME}. ${ARI_NAME} is the brain and canonical intelligence spine.`;
  }

  if (/(what is ace|define ace)/i.test(message)) {
    return `ACE means ${ACE_FULL_NAME}. ACE is the interface and manifestation layer around ${ARI_NAME}.`;
  }

  if (/(ari.+ace|ace.+ari|difference between ari and ace|ari vs ace)/i.test(lowered)) {
    return `${ARI_NAME} is the brain. ACE is the access layer. This app is ACE connecting you to ${ARI_NAME}, not a second brain.`;
  }

  if (/(who are you|what are you)/i.test(message)) {
    return `${ARI_NAME} is the private intelligence spine. This app is the ACE interface into it. In fallback mode I stay direct and can still handle notes, tasks, and workspace file actions.`;
  }

  if (/(what do you know about me|what do you know about alec|who am i)/i.test(message) && knownAboutAlec.length) {
    return `Known about Alec: ${knownAboutAlec.slice(0, 3).join(" | ")}.`;
  }

  if (/(what should i focus on|what should i work on|current priorities|priority)/i.test(lowered)) {
    if (priorities.length) {
      return `Current priority: ${priorities[0]}. ${currentFocus[0] ? `Current focus: ${currentFocus[0]}.` : workingStateSignals[0] ? `Working state: ${workingStateSignals[0]}.` : ""}`.trim();
    }
    if (currentFocus[0]) {
      return `Current focus: ${currentFocus[0]}. ${awarenessSummary || ""}`.trim();
    }
  }

  if (/(recent decisions|what changed|what did we decide)/i.test(lowered) && recentDecisions.length) {
    return `Recent decision: ${recentDecisions[0]}.`;
  }

  if (/(help|what can you do|capabilities)/i.test(message)) {
    return [
      "ARI is in deterministic fallback mode.",
      memoryHitCount ? `I found ${memoryHitCount} relevant memory item(s).` : "No relevant memory was retrieved for this turn.",
      operatorChannelLines[0] || "Operator channels are limited to the hub right now.",
      majorAutonomyBlocker ? `Current blocker: ${majorAutonomyBlocker}.` : "",
      "I can reliably handle notes, tasks, workspace file actions, and direct builder coordination right now.",
      "Best results come from explicit commands."
    ].join(" ");
  }

  return [
    "ARI is in deterministic fallback mode.",
    memoryHitCount ? `I found ${memoryHitCount} relevant memory item(s).` : "No relevant memory was retrieved for this turn.",
    awarenessSummary ? awarenessSummary : "",
    currentFocus[0] ? `Current focus item: ${currentFocus[0]}.` : "",
    priorities[0] ? `Current priority in memory: ${priorities[0]}.` : "No explicit current priority is stored yet.",
    tracking[0] ? `Tracking: ${tracking[0]}.` : "",
    operatorChannelLines[0] || "Operator channels remain limited to the hub surface.",
    majorAutonomyBlocker ? `Current blocker: ${majorAutonomyBlocker}.` : "",
    "I can execute notes, tasks, workspace file actions, and builder handoffs now.",
    "Give me a direct command or add a hosted model key for richer reasoning."
  ]
    .filter(Boolean)
    .join(" ");
}
