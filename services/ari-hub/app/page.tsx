type DashboardPanel = {
  title: string;
  status: "ready" | "partial" | "missing" | "disabled";
  source: string;
  lines: string[];
};

type SkillRow = {
  id: string;
  status: string;
  description: string;
};

const skills: SkillRow[] = [
  {
    id: "ari.native.coding_loop",
    status: "active",
    description: "Bounded coding-loop authority spine with approval, verification, and memory.",
  },
  {
    id: "ari.native.self_documentation",
    status: "prototype",
    description: "ContentSeed and ContentPackage generation from real ARI activity.",
  },
  {
    id: "ari.native.file_organization",
    status: "candidate",
    description: "Not active. First safe slice would be read-only scan and proposal.",
  },
  {
    id: "ari.native.document_processing",
    status: "candidate",
    description: "Not active. First safe slice would be local read-only extraction.",
  },
  {
    id: "ari.native.research_gathering",
    status: "candidate",
    description: "Not active. Requires explicit network authority before source gathering.",
  },
  {
    id: "ari.native.spreadsheet_analysis",
    status: "candidate",
    description: "Not active. Requires source-file and export authority boundaries.",
  },
  {
    id: "ari.native.email_calendar_triage",
    status: "candidate",
    description: "Not active. No account access, sending, or scheduling from this shell.",
  },
  {
    id: "ari.native.browser_inspection",
    status: "candidate",
    description: "Not active. Browser/session authority is not present in this dashboard.",
  },
];

const panels: DashboardPanel[] = [
  {
    title: "Overview",
    status: "partial",
    source: "docs/status/current-architecture.md",
    lines: [
      "ARI brain state is documented and inspectable.",
      "Unified live overview read model is still missing.",
      "ACE displays state only; it does not decide priorities.",
    ],
  },
  {
    title: "Skills",
    status: "ready",
    source: "api skills list --json",
    lines: [
      "Static catalog, router, readiness, and proposal objects exist.",
      "One active native skill and one prototype native skill are visible.",
      "Candidate skills remain inactive until ARI gates promote them.",
    ],
  },
  {
    title: "Skill readiness",
    status: "ready",
    source: "api skills readiness --id <skill_id> --json",
    lines: [
      "Readiness gates are evaluated by ARI.",
      "ACE must not promote, activate, or mark skills ready by itself.",
    ],
  },
  {
    title: "Missing-skill proposals",
    status: "ready",
    source: "api skills propose --goal <goal> --json",
    lines: [
      "Proposals describe the first bounded implementation slice.",
      "They do not build, load, execute, or persist a skill.",
    ],
  },
  {
    title: "Coding-loop chains",
    status: "ready",
    source: "api execution coding-loops chain --id <result_id>",
    lines: [
      "Chain inspection is an ARI-owned story of approvals, executions, and reviews.",
      "No advance, approve, reject, or execute controls are exposed here.",
    ],
  },
  {
    title: "Pending approvals",
    status: "ready",
    source: "api execution retry-approvals list",
    lines: [
      "Approval artifacts are inspectable through ARI.",
      "Controls are intentionally disabled in this first ACE dashboard shell.",
    ],
  },
  {
    title: "Memory / lifecycle lessons",
    status: "partial",
    source: "api memory explain coding-loop-chain",
    lines: [
      "Compact coding-loop lifecycle memory exists.",
      "A recent lifecycle lesson list is still a future read model.",
    ],
  },
  {
    title: "Self-documentation content",
    status: "partial",
    source: "api self-doc seed/package",
    lines: [
      "ContentSeed and ContentPackage CLI generation exist.",
      "No recording, voice, export, upload, or posting exists.",
    ],
  },
  {
    title: "System health",
    status: "missing",
    source: "future GET /system/health",
    lines: [
      "Current shell can show documented status only.",
      "Backend-owned health aggregation remains to be implemented.",
    ],
  },
];

const disabledControls = [
  "approve",
  "reject",
  "execute",
  "advance chain",
  "mutate memory",
  "create skills",
  "invoke tools",
  "external integrations",
];

export default function HomePage() {
  const activeSkills = skills.filter((skill) => skill.status === "active").length;
  const prototypeSkills = skills.filter((skill) => skill.status === "prototype").length;
  const candidateSkills = skills.filter((skill) => skill.status === "candidate").length;

  return (
    <main className="ace-readonly-shell">
      <section className="ace-readonly-hero" aria-labelledby="dashboard-title">
        <div>
          <p className="ace-readonly-kicker">ACE read-only dashboard shell</p>
          <h1 id="dashboard-title">ARI remains the brain. ACE displays state.</h1>
          <p className="ace-readonly-summary">
            This first product surface is local, diagnostic, and non-authoritative.
            It exposes the panel shape from the ACE read-only contract without owning
            decisions, approvals, execution, memory, skill selection, or independent state.
          </p>
        </div>
        <div className="ace-readonly-authority" aria-label="Authority boundary">
          <span>Authority boundary</span>
          <strong>No mutation controls</strong>
          <p>Future controls must call ARI backend authority surfaces.</p>
        </div>
      </section>

      <section className="ace-readonly-metrics" aria-label="ARI status summary">
        <div>
          <span>Active skills</span>
          <strong>{activeSkills}</strong>
        </div>
        <div>
          <span>Prototype skills</span>
          <strong>{prototypeSkills}</strong>
        </div>
        <div>
          <span>Candidate skills</span>
          <strong>{candidateSkills}</strong>
        </div>
        <div>
          <span>Dashboard mode</span>
          <strong>Read-only</strong>
        </div>
      </section>

      <section className="ace-readonly-grid" aria-label="ACE dashboard panels">
        {panels.map((panel) => (
          <article className="ace-readonly-panel" key={panel.title}>
            <div className="ace-readonly-panel-header">
              <h2>{panel.title}</h2>
              <span className={`ace-readonly-status ace-readonly-status-${panel.status}`}>
                {panel.status}
              </span>
            </div>
            <p className="ace-readonly-source">{panel.source}</p>
            <ul>
              {panel.lines.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </article>
        ))}
      </section>

      <section className="ace-readonly-section" aria-labelledby="skills-title">
        <div className="ace-readonly-section-heading">
          <p className="ace-readonly-kicker">Skill inventory</p>
          <h2 id="skills-title">Active, prototype, and candidate skills</h2>
        </div>
        <div className="ace-readonly-skill-list">
          {skills.map((skill) => (
            <article className="ace-readonly-skill-row" key={skill.id}>
              <div>
                <h3>{skill.id}</h3>
                <p>{skill.description}</p>
              </div>
              <span className={`ace-readonly-status ace-readonly-status-${skill.status}`}>
                {skill.status}
              </span>
            </article>
          ))}
        </div>
      </section>

      <section className="ace-readonly-section" aria-labelledby="disabled-title">
        <div className="ace-readonly-section-heading">
          <p className="ace-readonly-kicker">Disabled in this slice</p>
          <h2 id="disabled-title">Controls stay behind ARI authority</h2>
        </div>
        <div className="ace-readonly-disabled-list" aria-label="Disabled controls">
          {disabledControls.map((control) => (
            <span key={control}>{control}</span>
          ))}
        </div>
      </section>
    </main>
  );
}
