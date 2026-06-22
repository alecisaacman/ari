from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ...core.paths import PROJECT_ROOT


@dataclass(frozen=True, slots=True)
class SourceCommit:
    hash: str
    subject: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ContentSeed:
    seed_id: str
    source_commit_range: str
    source_commits: tuple[SourceCommit, ...]
    source_files: tuple[str, ...]
    title: str
    one_sentence_summary: str
    why_it_matters: str
    proof_points: tuple[str, ...]
    demo_idea: str
    hook_options: tuple[str, ...]
    visual_moments: tuple[str, ...]
    suggested_voiceover: str
    suggested_linkedin_post: str
    suggested_short_caption: str
    risk_notes: tuple[str, ...]
    redaction_notes: tuple[str, ...]
    claims_to_avoid: tuple[str, ...]
    next_content_angle: str
    created_at: str = field(default_factory=lambda: _now_iso())

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["source_commits"] = [commit.to_dict() for commit in self.source_commits]
        return payload


@dataclass(frozen=True, slots=True)
class GitCommandResult:
    stdout: str
    stderr: str = ""
    returncode: int = 0


GitRunner = Callable[[Sequence[str], Path], GitCommandResult]


def content_seed_from_dict(payload: Mapping[str, object]) -> ContentSeed:
    source_commits_raw = _required_sequence(payload, "source_commits")
    source_commits = tuple(_source_commit_from_dict(commit) for commit in source_commits_raw)
    return ContentSeed(
        seed_id=_required_str(payload, "seed_id"),
        source_commit_range=_required_str(payload, "source_commit_range"),
        source_commits=source_commits,
        source_files=_required_str_tuple(payload, "source_files"),
        title=_required_str(payload, "title"),
        one_sentence_summary=_required_str(payload, "one_sentence_summary"),
        why_it_matters=_required_str(payload, "why_it_matters"),
        proof_points=_required_str_tuple(payload, "proof_points"),
        demo_idea=_required_str(payload, "demo_idea"),
        hook_options=_required_str_tuple(payload, "hook_options"),
        visual_moments=_required_str_tuple(payload, "visual_moments"),
        suggested_voiceover=_required_str(payload, "suggested_voiceover"),
        suggested_linkedin_post=_required_str(payload, "suggested_linkedin_post"),
        suggested_short_caption=_required_str(payload, "suggested_short_caption"),
        risk_notes=_required_str_tuple(payload, "risk_notes"),
        redaction_notes=_required_str_tuple(payload, "redaction_notes"),
        claims_to_avoid=_required_str_tuple(payload, "claims_to_avoid"),
        next_content_angle=_required_str(payload, "next_content_angle"),
        created_at=_required_str(payload, "created_at"),
    )


def generate_content_seed_from_commits(
    *,
    from_ref: str,
    to_ref: str,
    repo_root: Path | str | None = None,
    test_output: str | None = None,
    user_framing: str | None = None,
    redaction_notes: Sequence[str] = (),
    git_runner: GitRunner | None = None,
) -> ContentSeed:
    root = Path(repo_root or PROJECT_ROOT).expanduser().resolve()
    runner = git_runner or _run_git
    source_range = f"{from_ref}..{to_ref}"
    commits = _load_commits(source_range, root, runner)
    files = _load_changed_files(source_range, root, runner)
    themes = _infer_themes(commits, files)
    risk_notes = _risk_notes(commits, files, test_output, user_framing)
    all_redaction_notes = tuple([*redaction_notes, *_redaction_notes(risk_notes)])
    proof_points = _proof_points(commits, files, test_output)
    title = _title(themes, commits)
    one_sentence = _one_sentence_summary(themes, commits, files)
    why_it_matters = _why_it_matters(themes)
    demo_idea = _demo_idea(themes, files)
    hook_options = _hook_options(themes)
    visual_moments = _visual_moments(themes, files)
    suggested_voiceover = _voiceover(title, why_it_matters, proof_points)
    suggested_linkedin_post = _linkedin_post(title, one_sentence, proof_points)
    suggested_short_caption = _short_caption(themes)
    claims_to_avoid = _claims_to_avoid(risk_notes)
    next_content_angle = _next_content_angle(themes)
    if user_framing:
        proof_points = (*proof_points, f"User-approved framing: {user_framing.strip()}")

    return ContentSeed(
        seed_id=f"content-seed-{uuid4()}",
        source_commit_range=source_range,
        source_commits=tuple(commits),
        source_files=tuple(files),
        title=title,
        one_sentence_summary=one_sentence,
        why_it_matters=why_it_matters,
        proof_points=tuple(proof_points),
        demo_idea=demo_idea,
        hook_options=hook_options,
        visual_moments=visual_moments,
        suggested_voiceover=suggested_voiceover,
        suggested_linkedin_post=suggested_linkedin_post,
        suggested_short_caption=suggested_short_caption,
        risk_notes=tuple(risk_notes),
        redaction_notes=all_redaction_notes,
        claims_to_avoid=claims_to_avoid,
        next_content_angle=next_content_angle,
    )


def _source_commit_from_dict(payload: object) -> SourceCommit:
    if not isinstance(payload, Mapping):
        raise ValueError("source_commits must contain objects.")
    return SourceCommit(
        hash=_required_str(payload, "hash"),
        subject=_required_str(payload, "subject"),
    )


def _required_str(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"ContentSeed field {key!r} is required and must be a string.")
    return value


def _required_sequence(payload: Mapping[str, object], key: str) -> tuple[object, ...]:
    value = payload.get(key)
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError(f"ContentSeed field {key!r} is required and must be a list.")
    return tuple(value)


def _required_str_tuple(payload: Mapping[str, object], key: str) -> tuple[str, ...]:
    values = _required_sequence(payload, key)
    if not all(isinstance(value, str) for value in values):
        raise ValueError(f"ContentSeed field {key!r} must contain only strings.")
    return tuple(values)


def _run_git(args: Sequence[str], cwd: Path) -> GitCommandResult:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return GitCommandResult(
        stdout=completed.stdout,
        stderr=completed.stderr,
        returncode=completed.returncode,
    )


def _load_commits(
    source_range: str,
    repo_root: Path,
    runner: GitRunner,
) -> list[SourceCommit]:
    result = runner(("log", "--reverse", "--format=%H%x1f%s", source_range), repo_root)
    if result.returncode != 0:
        raise ValueError(f"Unable to inspect git commits for {source_range}: {result.stderr}")
    commits: list[SourceCommit] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        if "\x1f" in line:
            commit_hash, subject = line.split("\x1f", 1)
        else:
            commit_hash, subject = line.strip(), ""
        commits.append(SourceCommit(hash=commit_hash.strip(), subject=subject.strip()))
    return commits


def _load_changed_files(
    source_range: str,
    repo_root: Path,
    runner: GitRunner,
) -> list[str]:
    result = runner(("diff", "--name-only", source_range), repo_root)
    if result.returncode != 0:
        raise ValueError(f"Unable to inspect changed files for {source_range}: {result.stderr}")
    return sorted({line.strip() for line in result.stdout.splitlines() if line.strip()})


def _infer_themes(commits: list[SourceCommit], files: list[str]) -> tuple[str, ...]:
    haystack = " ".join([*[commit.subject for commit in commits], *files]).lower()
    themes: list[str] = []
    keyword_themes = (
        ("self_documentation", ("self-documentation", "self documentation", "content seed")),
        ("skill_architecture", ("skill", "manifest", "inventory", "native skill")),
        ("ace_dashboard", ("ace", "dashboard", "read-only", "read model")),
        ("memory_learning", ("memory", "lifecycle", "learning")),
        ("approval_chain", ("approval", "chain", "retry", "authority")),
        ("verification", ("test", "pytest", "ruff", "verification")),
        ("docs", ("docs/", ".md", "document")),
    )
    for theme, keywords in keyword_themes:
        if any(keyword in haystack for keyword in keywords):
            themes.append(theme)
    return tuple(dict.fromkeys(themes)) or ("general_build_progress",)


def _risk_notes(
    commits: list[SourceCommit],
    files: list[str],
    test_output: str | None,
    user_framing: str | None,
) -> list[str]:
    haystack = "\n".join(
        [
            *[commit.subject for commit in commits],
            *files,
            test_output or "",
            user_framing or "",
        ]
    )
    checks = (
        (r"sk-[A-Za-z0-9_-]{12,}", "Possible API key-like string detected."),
        (r"(?i)\b(api[_-]?key|token|secret|credential|password)\b", "Secret-like term detected."),
        (r"(?m)(^|[/\\])\.env(?:[./\\]|$)", ".env reference detected."),
        (r"/Users/[^\s]+|/home/[^\s]+|C:\\Users\\[^\s]+", "Private absolute path detected."),
        (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "Email address detected."),
    )
    notes = [message for pattern, message in checks if re.search(pattern, haystack)]
    if not commits:
        notes.append("No commits were found in the requested range; avoid claiming shipped work.")
    return list(dict.fromkeys(notes))


def _redaction_notes(risk_notes: list[str]) -> list[str]:
    if not risk_notes:
        return ["No sensitive-looking input was detected by the first-pass scanner."]
    return [
        "Review and redact sensitive-looking inputs before public use.",
        *risk_notes,
    ]


def _proof_points(
    commits: list[SourceCommit],
    files: list[str],
    test_output: str | None,
) -> tuple[str, ...]:
    points: list[str] = [
        f"Commit {commit.hash[:12]}: {commit.subject or '<no subject>'}"
        for commit in commits[:5]
    ]
    if len(commits) > 5:
        points.append(f"{len(commits) - 5} additional commit(s) are in the range.")
    if files:
        points.append(f"Changed {len(files)} file(s): {', '.join(files[:6])}.")
    if test_output:
        summary = _compact_line(test_output)
        points.append(f"Test output supplied: {summary}")
    if not points:
        points.append("No concrete commits or files were available for this seed.")
    return tuple(points)


def _title(themes: tuple[str, ...], commits: list[SourceCommit]) -> str:
    if "self_documentation" in themes:
        return "ARI starts turning its own build history into content seeds"
    if "skill_architecture" in themes:
        return "ARI formalizes native skills without creating a second brain"
    if "ace_dashboard" in themes:
        return "ACE gets a read-only contract over ARI state"
    if "memory_learning" in themes:
        return "ARI captures compact lifecycle memory from real work"
    if commits:
        return f"ARI build update: {commits[-1].subject}"
    return "ARI build update from local evidence"


def _one_sentence_summary(
    themes: tuple[str, ...],
    commits: list[SourceCommit],
    files: list[str],
) -> str:
    return (
        f"This seed summarizes {len(commits)} commit(s) touching {len(files)} file(s), "
        f"with primary themes: {', '.join(themes)}."
    )


def _why_it_matters(themes: tuple[str, ...]) -> str:
    if "self_documentation" in themes:
        return (
            "It gives ARI a factual path to explain and demonstrate its own build "
            "process without inventing progress."
        )
    if "skill_architecture" in themes:
        return "It keeps skills bounded under ARI's shared authority spine."
    if "ace_dashboard" in themes:
        return "It lets ACE display ARI state without becoming the brain."
    if "memory_learning" in themes:
        return "It turns execution history into compact lessons ARI can reuse."
    return "It documents concrete progress from local repository evidence."


def _demo_idea(themes: tuple[str, ...], files: list[str]) -> str:
    if "self_documentation" in themes:
        return "Show a commit range becoming a factual content seed with risks and claims-to-avoid."
    if "skill_architecture" in themes:
        return "Show the skill contract, inventory, and manifest side by side."
    if "ace_dashboard" in themes:
        return "Show the read-only dashboard contract and explain what ACE cannot control."
    if "memory_learning" in themes:
        return "Show lifecycle memory evidence linked back to execution records."
    if files:
        return f"Show the changed files list and explain the smallest real improvement: {files[0]}."
    return "Show the local evidence ARI used before making any public-facing claim."


def _hook_options(themes: tuple[str, ...]) -> tuple[str, ...]:
    if "self_documentation" in themes:
        return (
            "What if your AI system could document its own build without making things up?",
            "ARI is learning how to turn real commits into factual demos.",
            "This is not a hype generator. It is evidence-backed self-documentation.",
        )
    if "skill_architecture" in themes:
        return (
            "ARI is becoming a brain that can use skills without spawning mini-agents.",
            "The coding loop is now one skill, not the whole architecture.",
            "A skill contract keeps future capabilities from becoming competing brains.",
        )
    return (
        "Here is what changed in ARI, backed by commits and tests.",
        "This build slice is small, but it compounds.",
        "ARI is turning local evidence into inspectable progress.",
    )


def _visual_moments(themes: tuple[str, ...], files: list[str]) -> tuple[str, ...]:
    moments = ["Show the commit range and changed files used as evidence."]
    if "self_documentation" in themes:
        moments.append("Show the generated ContentSeed fields and claims_to_avoid.")
    if "skill_architecture" in themes:
        moments.append("Show the skill inventory highlighting active vs candidate skills.")
    if "ace_dashboard" in themes:
        moments.append("Show the read-only dashboard contract's allowed/not-allowed lists.")
    if files:
        moments.append(f"Open {files[0]} as the concrete artifact behind the seed.")
    return tuple(moments)


def _voiceover(title: str, why_it_matters: str, proof_points: tuple[str, ...]) -> str:
    first_proof = proof_points[0] if proof_points else "The source evidence is local."
    return f"{title}. {why_it_matters} Proof point: {first_proof}"


def _linkedin_post(
    title: str,
    one_sentence_summary: str,
    proof_points: tuple[str, ...],
) -> str:
    bullets = "\n".join(f"- {point}" for point in proof_points[:3])
    return f"{title}\n\n{one_sentence_summary}\n\nEvidence:\n{bullets}"


def _short_caption(themes: tuple[str, ...]) -> str:
    if "self_documentation" in themes:
        return "ARI is turning real build evidence into factual content seeds."
    if "skill_architecture" in themes:
        return "ARI is learning skills without creating a second brain."
    return "A small ARI build slice, grounded in real commits."


def _claims_to_avoid(risk_notes: list[str]) -> tuple[str, ...]:
    claims = [
        "Do not claim this feature records, edits, exports, or publishes media.",
        "Do not claim ARI has a runtime skill registry.",
        "Do not claim candidate skills are active.",
        "Do not imply autonomy beyond the provided evidence.",
    ]
    if risk_notes:
        claims.append("Do not publish raw inputs before redaction review.")
    return tuple(claims)


def _next_content_angle(themes: tuple[str, ...]) -> str:
    if "self_documentation" in themes:
        return "Show the first implementation generating a seed from a commit range."
    if "skill_architecture" in themes:
        return "Explain how the next native skill will prove the contract."
    if "ace_dashboard" in themes:
        return "Map read-only dashboard panels to canonical ARI sources."
    return "Pick one proof point and turn it into a short terminal demo."


def _compact_line(text: str, limit: int = 180) -> str:
    line = " ".join(part.strip() for part in text.splitlines() if part.strip())
    if len(line) <= limit:
        return line
    return f"{line[: limit - 3]}..."


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
