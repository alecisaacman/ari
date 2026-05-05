import { getDashboardOverview } from "@/src/core/ari-spine/overview-bridge";
import type { AriOperatingOverview, OverviewMetric, OverviewSkill } from "@/src/core/ari-spine/overview-bridge";

export const dynamic = "force-dynamic";

type DashboardPanel = {
  title: string;
  status: "ready" | "partial" | "missing" | "disabled";
  source: string;
  lines: string[];
};

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

export default async function HomePage() {
  const result = await getDashboardOverview();
  const overview = result.overview;
  const panels = buildPanels(overview, result.source);
  const skills = [
    ...overview.active_skills,
    ...overview.prototype_skills,
    ...overview.candidate_skills,
  ];

  return (
    <main className="ace-readonly-shell">
      <section className="ace-readonly-hero" aria-labelledby="dashboard-title">
        <div>
          <p className="ace-readonly-kicker">ACE read-only dashboard shell</p>
          <h1 id="dashboard-title">ARI remains the brain. ACE displays state.</h1>
          <p className="ace-readonly-summary">{overview.doctrine_summary}</p>
          {result.source === "static-fallback" ? (
            <p className="ace-readonly-warning">
              Static fallback active: {result.error ?? "ARI overview unavailable."}
            </p>
          ) : null}
        </div>
        <div className="ace-readonly-authority" aria-label="Authority boundary">
          <span>Authority boundary</span>
          <strong>No mutation controls</strong>
          <p>{overview.authority_warning}</p>
        </div>
      </section>

      <section className="ace-readonly-metrics" aria-label="ARI status summary">
        <div>
          <span>Active skills</span>
          <strong>{overview.active_skill_count}</strong>
        </div>
        <div>
          <span>Prototype skills</span>
          <strong>{overview.prototype_skill_count}</strong>
        </div>
        <div>
          <span>Candidate skills</span>
          <strong>{overview.candidate_skill_count}</strong>
        </div>
        <div>
          <span>Pending approvals</span>
          <strong>{metricValueLabel(overview.pending_approval_count)}</strong>
        </div>
        <div>
          <span>Coding-loop results</span>
          <strong>{metricValueLabel(overview.recent_coding_loop_count)}</strong>
        </div>
        <div>
          <span>Lifecycle lessons</span>
          <strong>{metricValueLabel(overview.recent_lifecycle_lesson_count)}</strong>
        </div>
        <div>
          <span>Counts source</span>
          <strong>
            {overview.counts_generated_from_live_sources ? "live" : "partial"}
          </strong>
        </div>
        <div>
          <span>Overview source</span>
          <strong>{result.source}</strong>
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
        {skills.length ? (
          <div className="ace-readonly-skill-list">
            {skills.map((skill) => (
              <SkillRow skill={skill} key={skill.skill_id} />
            ))}
          </div>
        ) : (
          <p className="ace-readonly-empty">
            Skill inventory is unavailable until ACE can read the ARI-owned overview.
          </p>
        )}
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

function SkillRow({ skill }: { skill: OverviewSkill }) {
  return (
    <article className="ace-readonly-skill-row">
      <div>
        <h3>{skill.skill_id}</h3>
        <p>{skill.name}</p>
        <p>{skill.implementation_status}</p>
      </div>
      <span className={`ace-readonly-status ace-readonly-status-${skill.lifecycle_status}`}>
        {skill.lifecycle_status}
      </span>
    </article>
  );
}

function buildPanels(
  overview: AriOperatingOverview,
  source: "ari-api" | "static-fallback",
): DashboardPanel[] {
  return [
    {
      title: "Overview",
      status: source === "ari-api" ? "ready" : "partial",
      source: source === "ari-api" ? "GET /overview" : "static fallback",
      lines: [
        `Generated at: ${overview.generated_at}`,
        `Dashboard mode: ${overview.dashboard_mode}`,
        `Summary counts: ${
          overview.counts_generated_from_live_sources ? "live" : "partial"
        }`,
        overview.partial_counts_reason ?? "All summary count sources are readable.",
        overview.next_recommended_inspection,
      ],
    },
    {
      title: "Skills",
      status: source === "ari-api" ? "ready" : "partial",
      source: "api skills list --json / GET /overview",
      lines: [
        `${overview.active_skill_count} active skill(s).`,
        `${overview.prototype_skill_count} prototype skill(s).`,
        `${overview.candidate_skill_count} candidate skill(s).`,
      ],
    },
    {
      title: "Skill readiness",
      status: "ready",
      source: "api skills readiness --id <skill_id> --json",
      lines: [
        "Readiness gates remain ARI-owned.",
        "ACE may display readiness but must not promote or activate skills.",
      ],
    },
    {
      title: "Missing-skill proposals",
      status: "ready",
      source: "api skills propose --goal <goal> --json",
      lines: [
        "Proposals describe bounded first slices.",
        "No proposal is executed, persisted, or built by ACE.",
      ],
    },
    {
      title: "Coding-loop chains",
      status: metricPanelStatus(overview.recent_coding_loop_count),
      source: "api execution coding-loops chain --id <result_id>",
      lines: metricLines(overview.recent_coding_loop_count),
    },
    {
      title: "Pending approvals",
      status: metricPanelStatus(overview.pending_approval_count),
      source: "api execution retry-approvals list",
      lines: metricLines(overview.pending_approval_count),
    },
    {
      title: "Memory / lifecycle lessons",
      status: metricPanelStatus(overview.recent_lifecycle_lesson_count),
      source: "api memory explain coding-loop-chain",
      lines: metricLines(overview.recent_lifecycle_lesson_count),
    },
    {
      title: "Self-documentation content",
      status: source === "ari-api" ? "partial" : "missing",
      source: "api self-doc seed/package",
      lines: [overview.self_documentation_status],
    },
    {
      title: "System health",
      status: source === "ari-api" ? "partial" : "missing",
      source: "future GET /system/health",
      lines: [
        ...overview.read_model_notes,
        `Unavailable counts: ${
          overview.unavailable_counts.length
            ? overview.unavailable_counts.join(", ")
            : "none"
        }`,
      ],
    },
  ];
}

function metricPanelStatus(metric: OverviewMetric): DashboardPanel["status"] {
  return metric.value === null ? "partial" : "ready";
}

function metricLines(metric: OverviewMetric): string[] {
  const value = metric.value === null ? "unavailable" : String(metric.value);
  return [`Value: ${value}`, `Status: ${metric.status}`, metric.reason];
}

function metricValueLabel(metric: OverviewMetric): string {
  return metric.value === null ? "partial" : String(metric.value);
}
