import assert from "node:assert/strict";
import test from "node:test";

import { classifyBuilderOutput } from "../src/core/orchestration/classifier";

test("orchestration classifier covers strict routing states", () => {
  const autoPass = classifyBuilderOutput("Tests passed. Minor update: helper text is shorter.");
  assert.equal(autoPass.classification, "auto_pass");
  assert.equal(autoPass.escalationRequired, false);

  const autoSummarize = classifyBuilderOutput(
    [
      "Implemented the activity feed slice.",
      "Added approvals, background runtime hooks, and verification notes.",
      "npm test passed.",
      "npm run build passed.",
      "Updated files:",
      "- src/core/api/services.ts",
      "- src/components/ace/ace-console.tsx",
      "- src/core/agent/background-runtime.ts",
      "- tests/api.test.ts",
      "- tests/orchestration.test.ts",
      "Next step remains small and runtime-focused."
    ].join("\n")
  );
  assert.equal(autoSummarize.classification, "auto_summarize");
  assert.equal(autoSummarize.escalationRequired, false);

  const escalation = classifyBuilderOutput("Architecture tradeoff: this changes canonical source-of-truth boundaries and needs a direction decision.");
  assert.equal(escalation.classification, "escalate_to_alec");
  assert.equal(escalation.escalationRequired, true);
});
