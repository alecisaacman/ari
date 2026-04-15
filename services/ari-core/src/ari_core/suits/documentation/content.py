import argparse
import random
from datetime import date
from pathlib import Path
from typing import Dict, List

from ...core.paths import DB_PATH
from ...modules.networking.db import get_connection


MODE_SETTINGS: Dict[str, Dict[str, object]] = {
    "short": {
        "reflection": False,
        "extra_context": False,
        "forward": "make the path from execution to publishing feel almost frictionless.",
    },
    "balanced": {
        "reflection": True,
        "extra_context": False,
        "forward": "pull more context from active projects so each draft stays close to the work that created it.",
    },
    "detailed": {
        "reflection": True,
        "extra_context": True,
        "forward": "deepen that path so ARI can turn more raw project state into sharper drafts, stronger distribution, and a clearer public trail of the work.",
    },
}

STYLE_SETTINGS: Dict[str, Dict[str, str]] = {
    "balanced": {
        "hook_prefix": "One thing I keep returning to in ARI is",
        "built_open": "I built a thin local drafting layer around {topic} so the post starts close to the work instead of hours after it.",
        "lesson": "The useful lesson is that good updates usually come from capturing the real tradeoff while it is still live.",
        "matters_open": "That matters because execution gets more valuable when the reasoning around it is easy to share.",
        "matters_close": "For ARI, the point is not more content. It is better signal from actual work.",
        "forward": "I want the next version to feel even more native to the daily workflow.",
    },
    "story": {
        "hook_prefix": "A real thread in building ARI has been",
        "built_open": "I built this as part of the builder loop around {topic}. I wanted a draft layer that sounds like the work actually felt while I was in it.",
        "lesson": "What I keep learning is that the story gets weaker when I wait too long to write it down.",
        "matters_open": "That matters because projects usually look cleaner in hindsight than they did in motion.",
        "matters_close": "I would rather share the path while it is being formed than polish away the interesting parts.",
        "forward": "I want to keep tightening that loop so the public trail stays close to the builder journey.",
    },
    "tactical": {
        "hook_prefix": "One concrete thing I have been working through is",
        "built_open": "I built a narrow drafting command around {topic} so I can turn implementation work into a usable post without leaving the local workflow.",
        "lesson": "The practical lesson is that smaller, sharper prompts produce better drafts than broad ones.",
        "matters_open": "That matters because communication overhead is often what breaks the habit of sharing useful work.",
        "matters_close": "If the draft can come directly out of the command surface, the process is easier to repeat.",
        "forward": "Next I want to make the drafting path faster, tighter, and easier to reuse after each build cycle.",
    },
    "insight": {
        "hook_prefix": "The systems question underneath this for me is",
        "built_open": "I have been using {topic} as a way to test whether ARI can turn raw execution into a clearer operating narrative.",
        "lesson": "The main insight is that a tool becomes more useful when it helps interpret the work, not just store it.",
        "matters_open": "That matters because systems compound faster when they improve both action and legibility.",
        "matters_close": "A local-first content layer is small on the surface, but it changes how the system thinks about its own output.",
        "forward": "Next I want to keep pushing ARI toward a tighter connection between execution, interpretation, and communication.",
    },
}

POINT_LINES = [
    "The point was not to build a full writing system.",
    "This was never meant to become a full writing system.",
    "I was not trying to build a full writing system here.",
]

CAPTURE_SIGNAL_LINES = [
    "It was to create a useful local command that can catch the signal before it gets flattened.",
    "It was to make a local command that catches the signal before it gets sanded down.",
    "It was to create a local command that keeps the useful signal intact before it turns generic.",
]

SYSTEM_LINES = [
    "A strong local system should help ship the work and make the work easier to explain.",
    "A strong system should make it easier to publish the work and easier to articulate what actually happened.",
    "A solid local system should reduce the gap between doing the work and explaining the work.",
]

EXECUTION_GROUNDED_LINES = [
    "That is the part I care about most for ARI: a drafting layer that stays grounded in execution instead of drifting into generic commentary.",
    "That is the part I care about most for ARI: keeping the draft close to execution instead of letting it slide into generic commentary.",
    "For ARI, that is the real bar: the draft should stay tied to the work instead of turning into filler.",
]

SPECIFICITY_LINES = [
    "When the system can help shape the post right after the work happens, the draft keeps more specificity and less filler.",
    "If the draft starts right after the work, it tends to keep the useful specifics and lose a lot less signal.",
    "The closer the draft sits to the work itself, the more specificity it keeps and the less filler it needs.",
]

COMPOUNDING_LINES = [
    "If that translation from project state to communication gets easier, the system becomes more reusable and more compounding.",
    "If project state can turn into communication with less friction, the system becomes easier to reuse and more compounding over time.",
    "When that translation layer gets tighter, the system becomes more reusable and more likely to compound.",
]

HUMAN_OPENERS = {
    "built": [
        "What I am starting to notice is this:",
        "The thing that surprised me here is this:",
        "One thing that became clear quickly is this:",
    ],
    "matters": [
        "What keeps standing out to me is this:",
        "The broader pattern here is this:",
        "The part that feels most real to me is this:",
    ],
}

LESSON_VARIATIONS = {
    "balanced": [
        "The useful lesson is that good updates usually come from capturing the real tradeoff while it is still live.",
        "The useful lesson here is that the best updates usually come from catching the real tradeoff while it is still live.",
        "The lesson is that strong updates usually come from writing down the real tradeoff before hindsight smooths it out.",
    ],
    "story": [
        "What I keep learning is that the story gets weaker when I wait too long to write it down.",
        "I keep learning that the story loses something when I wait too long to write it down.",
        "The lesson for me is that the story gets thinner when I wait too long to capture it.",
    ],
    "tactical": [
        "The practical lesson is that smaller, sharper prompts produce better drafts than broad ones.",
        "The practical lesson here is that narrower, sharper prompts produce better drafts than broad ones.",
        "The practical lesson so far is that tighter prompts produce stronger drafts than broad ones.",
    ],
    "insight": [
        "The main insight is that a tool becomes more useful when it helps interpret the work, not just store it.",
        "The main insight here is that a tool becomes more useful when it helps interpret the work instead of only storing it.",
        "The insight that keeps holding up is that a tool gets more useful when it helps interpret the work, not just record it.",
    ],
}

FORWARD_TRANSITIONS = [
    "From here, ARI should",
    "The next step is for ARI to",
    "From here, the goal is for ARI to",
]

SHORT_BUILD_LINES = {
    "balanced": "I built a thin local drafting layer around {topic} to catch the signal while the tradeoff is still live.",
    "story": "I built this around {topic} to capture what the work actually felt like while I was still in it.",
    "tactical": "I built a narrow drafting command around {topic} so implementation work can turn into a usable post inside the local workflow.",
    "insight": "I used {topic} to test whether ARI can turn raw execution into a clearer operating narrative.",
}

SHORT_MATTERS_LINES = {
    "balanced": "It matters because better systems should make the work easier to ship and easier to explain.",
    "story": "It matters because I would rather share the shape of the work while it is forming than polish it into something flatter later.",
    "tactical": "It matters because communication overhead is usually what breaks the habit of sharing useful work.",
    "insight": "It matters because systems compound faster when they improve both action and legibility.",
}

VIDEO_SCRIPT_STYLE_SETTINGS: Dict[str, Dict[str, List[str]]] = {
    "balanced": {
        "hook": [
            "I did not expect {topic} to become one of the clearest tests for ARI.",
            "One of the most useful threads I have been building into ARI is this: {topic}.",
            "A surprisingly good test for ARI has been this: {topic}.",
        ],
        "context_open": [
            "Right now ARI is still a local execution system I use every day.",
            "ARI is still intentionally local-first, and that is the point.",
            "I am building ARI as a real command surface, not a concept deck.",
        ],
        "context_build": [
            "So I added a thin script layer that sits on top of the existing content flow.",
            "I wanted a script command that grows out of the work already happening in the system.",
            "The goal was to let the content layer turn live project work into something I can actually say out loud.",
        ],
        "core_open": [
            "What clicked for me is that the script does not need to do much.",
            "The useful lesson is that this layer can stay very small.",
            "The main thing I learned is that the script layer should stay thin.",
        ],
        "core_middle": [
            "It just needs a strong hook, a little context, the core idea, and a clean close.",
            "It just needs to pull out the signal, keep it conversational, and stop before it gets bloated.",
            "It just needs to catch the real point of the work before the language turns generic.",
        ],
        "core_why": [
            "The closer the script stays to the system, the more honest it sounds.",
            "A local-first tool should help explain the work, not just store it.",
            "Execution gets more leverage when the explanation is easy to speak.",
        ],
        "close": [
            "This feels like the bridge from written updates into video.",
            "It is a small layer, but it opens the door to a bigger media loop later.",
            "For now, I just want the script to feel real when I say it out loud.",
        ],
    },
    "story": {
        "hook": [
            "I keep noticing that this has turned into a real builder story inside ARI: {topic}.",
            "A funny part of building ARI is that {topic} ended up mattering more than I expected.",
            "One part of the ARI journey that keeps getting more interesting is {topic}.",
        ],
        "context_open": [
            "I am building ARI as this local execution engine I can actually live inside.",
            "Most of ARI has been built from real daily friction, not from a roadmap doc.",
            "ARI keeps growing out of things I actually need in the middle of work.",
        ],
        "context_build": [
            "And this week that led me to a short-form script command.",
            "That is what pulled me toward building a short video script layer.",
            "So I added a simple script layer on top of the existing content engine.",
        ],
        "core_open": [
            "The thing I learned is that the story gets better when I capture it early.",
            "What became clear is that the spoken version of the work needs its own shape.",
            "The lesson for me is that video starts with rhythm, not volume.",
        ],
        "core_middle": [
            "A few short sections are enough to keep the arc clear without sounding rehearsed.",
            "If I keep the lines short, the script sounds like me instead of a writing robot.",
            "The simple structure makes it easier to keep the thread honest while the work is still fresh.",
        ],
        "core_why": [
            "I want to share the path while I am still in it.",
            "I do not want the interesting parts to disappear under polish.",
            "The real texture of the work is usually in the first draft of the story.",
        ],
        "close": [
            "It feels like a better way to document the journey while it is still alive.",
            "I think this is how ARI starts sounding more human in public.",
            "This is still lean, but it already feels closer to how I would actually tell the story.",
        ],
    },
    "tactical": {
        "hook": [
            "Here is a practical thing I built into ARI: {topic}.",
            "One concrete ARI upgrade I just shipped is around {topic}.",
            "A very practical test for ARI has been this: {topic}.",
        ],
        "context_open": [
            "ARI already has a local content flow, command surface, and runtime state.",
            "The base system already has local commands, content generation, and project context.",
            "The existing ARI stack already had the content engine and local context pieces in place.",
        ],
        "context_build": [
            "So I added a thin `script short-video` command on top of that.",
            "I used that foundation to add a narrow short-video script command.",
            "I kept the change small and added a script layer instead of a whole media system.",
        ],
        "core_open": [
            "The implementation is deliberately simple.",
            "I kept the logic very lean on purpose.",
            "The useful part is how little logic this actually needs.",
        ],
        "core_middle": [
            "It uses section templates, small phrase pools, style switches, and a hard cap on length.",
            "It reuses the content patterns, varies phrasing with small pools, and keeps the output in a spoken range.",
            "It stays readable because it only has to assemble a hook, context, core idea, and close.",
        ],
        "core_why": [
            "Most creator workflows break when the tool gets too heavy.",
            "The habit only sticks if the command is fast and repeatable.",
            "A thin layer is easier to trust, test, and extend later.",
        ],
        "close": [
            "Next step is to keep testing whether the output actually sounds natural on camera.",
            "It is not media generation yet. It is the script layer the rest can build on.",
            "This is the part I wanted first: a command that turns work into something usable fast.",
        ],
    },
    "insight": {
        "hook": [
            "The deeper systems question inside {topic} is how ARI should translate work into narrative.",
            "What {topic} is really testing is whether ARI can interpret its own work clearly.",
            "The interesting systems problem behind {topic} is legibility.",
        ],
        "context_open": [
            "ARI is gradually becoming both an execution system and a way of making that execution legible.",
            "I keep thinking about ARI as both an operating system for work and an interpretation layer around it.",
            "The project is still local-first, but the larger point is how the system explains itself.",
        ],
        "context_build": [
            "That is why a short-form script command matters more than it sounds.",
            "So I added a small script layer to the existing content engine.",
            "That led me to build a very lean script command on top of the current content flow.",
        ],
        "core_open": [
            "The insight is that explanation needs its own interface.",
            "What clicked is that communication should be treated like a system output.",
            "The useful realization is that spoken clarity is part of system design too.",
        ],
        "core_middle": [
            "A good script is not just shorter text. It is structured language that can survive speech.",
            "The format only works if the lines are short, grounded, and close to the actual work.",
            "Once the output is shaped for speech, the system becomes easier to share without losing signal.",
        ],
        "core_why": [
            "Tools compound faster when they improve both action and interpretation.",
            "A system is more valuable when it can expose its reasoning cleanly.",
            "Legibility is part of leverage, not an extra layer on top of it.",
        ],
        "close": [
            "So this feels like a small feature with larger implications.",
            "It is a narrow addition, but it changes how I think about the system boundary.",
            "For me, this is where content stops being separate from the operating system.",
        ],
    },
}

HOOK_STYLE_POOLS: Dict[str, List[str]] = {
    "pattern_interrupt": [
        "I stopped trying to explain {topic} the polished way.",
        "I do not approach {topic} the old way anymore.",
        "I stopped treating {topic} like a writing problem.",
    ],
    "bold_statement": [
        "Most people think about {topic} the wrong way.",
        "Almost nobody shapes {topic} for speech first.",
        "Most people make {topic} sound cleaner than it really is.",
    ],
    "curiosity": [
        "{topic} changed how I think about ARI.",
        "This changed how I think about {topic}.",
        "One small change in {topic} completely changed my workflow.",
    ],
    "direct_statement": [
        "Here is what I just built around {topic}.",
        "I added something new to ARI around {topic}.",
        "Here is the ARI upgrade I just made for {topic}.",
    ],
}

HOOK_FOLLOW_LINES = [
    "It made the gap obvious.",
    "It changed how I write for camera.",
    "It made the next layer clearer.",
    "It exposed what was missing.",
]

WHY_LINES = [
    "The reason this matters is simple:",
    "Here is why this actually matters:",
    "This is where it starts to matter:",
]

PAUSE_LINES = [
    "That is the shift.",
    "That is the point.",
    "That is where this gets interesting.",
]

CREATOR_CLOSE_LINES = [
    "Next I am testing how fast this turns real work into a script I would actually record.",
    "The next step is making the output sharper on camera without adding more system weight.",
    "Now I want to push this further by testing it against more real build threads inside ARI.",
]


def _normalize_topic(topic: str) -> str:
    normalized = topic.strip()
    if not normalized:
        raise ValueError("Topic is required.")
    return normalized


def _normalize_style(style: str) -> str:
    if style is None:
        return "balanced"
    normalized = style.strip().lower()
    if normalized not in STYLE_SETTINGS:
        supported = ", ".join(sorted(STYLE_SETTINGS))
        raise ValueError(f"Unsupported style: {style}. Supported styles: {supported}")
    return normalized


def _count_rows(db_path: Path, table_name: str) -> int:
    if not db_path.exists():
        return 0

    with get_connection(db_path) as connection:
        row = connection.execute(f"select count(*) as count from {table_name}").fetchone()
    return int(row["count"])


def get_project_context(topic: str, db_path: Path = DB_PATH) -> dict[str, object]:
    context = {
        "topic": _normalize_topic(topic),
        "project_name": "ARI",
        "project_summary": (
            "ARI is being shaped into a local execution system that can help build, track, "
            "and now start documenting the work it creates."
        ),
        "contacts_count": 0,
        "notes_count": 0,
        "followups_count": 0,
        "has_runtime_context": False,
    }

    for table_name, key in (
        ("contacts", "contacts_count"),
        ("notes", "notes_count"),
        ("follow_ups", "followups_count"),
    ):
        try:
            context[key] = _count_rows(db_path=db_path, table_name=table_name)
        except Exception:
            context[key] = 0

    context["has_runtime_context"] = any(
        context[key] for key in ("contacts_count", "notes_count", "followups_count")
    )
    return context


def _pluralize(value: int, singular: str, plural: str) -> str:
    return singular if value == 1 else plural


def _compose_context_line(context: dict[str, object], include_detail: bool = False) -> str:
    if context["has_runtime_context"]:
        contacts_count = int(context["contacts_count"])
        notes_count = int(context["notes_count"])
        followups_count = int(context["followups_count"])
        line = (
            "It is already grounded in real local workflows: "
            f"{contacts_count} {_pluralize(contacts_count, 'contact', 'contacts')}, "
            f"{notes_count} {_pluralize(notes_count, 'note', 'notes')}, and "
            f"{followups_count} {_pluralize(followups_count, 'follow-up', 'follow-ups')} "
            "are already moving through the system."
        )
        if include_detail:
            line += (
                " That changes the quality of the draft because it is being shaped by live operating context, not a blank page."
            )
        return line

    line = (
        "It is still intentionally thin, but it already sits on top of the local CLI, "
        "SQLite state, and daily command surface ARI is building out."
    )
    if include_detail:
        line += (
            " That constraint is useful because anything that is not helpful locally is probably still too abstract."
        )
    return line


def _compose_hook(topic: str, style: str) -> str:
    style_value = _normalize_style(style)
    style_config = STYLE_SETTINGS[style_value]
    lowered = topic.lower()
    if lowered.startswith("why "):
        if style_value == "story":
            return f"One part of the builder journey I keep returning to is {topic}."
        if style_value == "tactical":
            return f"One concrete question behind the work is {topic}."
        if style_value == "insight":
            return f"The systems question I keep returning to is {topic}."
        return f"The question I keep coming back to in ARI is {topic}."
    if lowered.startswith(("how ", "what ")):
        if style_value == "story":
            return f"One live thread in building ARI has been {topic}."
        if style_value == "tactical":
            return f"One concrete thing I have been working through is {topic}."
        if style_value == "insight":
            return f"The systems question underneath this for me is {topic}."
        return f"One thing I keep returning to in ARI is {topic}."
    return f"{style_config['hook_prefix']} {topic}."


def _mode_config(mode: str) -> Dict[str, object]:
    try:
        return MODE_SETTINGS[mode]
    except KeyError as exc:
        raise ValueError(f"Unsupported mode: {mode}") from exc


def _style_config(style: str) -> Dict[str, str]:
    return STYLE_SETTINGS[_normalize_style(style)]


def _pick(options: List[str]) -> str:
    return random.choice(options)


def _maybe_human_opener(section: str, mode: str) -> str:
    if mode == "short":
        return ""
    return f"{_pick(HUMAN_OPENERS[section])} " if random.choice([False, False, True]) else ""


def _style_lesson(style: str) -> str:
    return _pick(LESSON_VARIATIONS[_normalize_style(style)])


def _resolve_mode(args: argparse.Namespace) -> str:
    if getattr(args, "detailed", False):
        return "detailed"
    if getattr(args, "short", False):
        return "short"
    return "balanced"


def _compose_built_learned_section(topic: str, context: dict[str, object], mode: str, style: str) -> str:
    config = _mode_config(mode)
    style_config = _style_config(style)
    sentences: List[str] = [
        style_config["built_open"].format(topic=topic),
        f"{_maybe_human_opener('built', mode)}{_pick(POINT_LINES)} {_pick(CAPTURE_SIGNAL_LINES)}",
        _compose_context_line(context, include_detail=bool(config["extra_context"])),
    ]

    if bool(config["reflection"]):
        sentences.append(_style_lesson(style))

    if bool(config["extra_context"]):
        sentences.append(_pick(SPECIFICITY_LINES))

    return " ".join(sentences)


def _compose_why_it_matters_section(mode: str, style: str) -> str:
    config = _mode_config(mode)
    style_config = _style_config(style)
    sentences: List[str] = [
        style_config["matters_open"],
        f"{_maybe_human_opener('matters', mode)}{_pick(SYSTEM_LINES)}",
        style_config["matters_close"],
    ]

    if bool(config["reflection"]):
        sentences.append(_pick(EXECUTION_GROUNDED_LINES))

    if bool(config["extra_context"]):
        sentences.append(_pick(COMPOUNDING_LINES))

    return " ".join(sentences)


def _compose_forward_looking_line(mode: str, style: str) -> str:
    config = _mode_config(mode)
    style_config = _style_config(style)
    if mode == "short":
        return style_config["forward"]
    forward_line = style_config["forward"]
    if "I want" in forward_line:
        transition = _pick(FORWARD_TRANSITIONS)
        return f"{forward_line} {transition} {config['forward']}"
    return f"{forward_line} From here, I want ARI to {config['forward']}"


def _compose_short_format(topic: str, context: dict[str, object], mode: str, style: str) -> str:
    sentences: List[str] = [_compose_hook(topic, style)]

    build_line = SHORT_BUILD_LINES[style].format(topic=topic)
    sentences.append(build_line)

    matters_line = SHORT_MATTERS_LINES[style]
    if context["has_runtime_context"] and mode != "short":
        matters_line = matters_line.rstrip(".") + ", and it already has live local context behind it."
    sentences.append(matters_line)

    return " ".join(sentences)


def _save_draft(draft: str) -> Path:
    output_dir = Path.home() / "ARI" / "content"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{date.today().isoformat()}.txt"
    output_path.write_text(draft + "\n", encoding="utf-8")
    return output_path


def _word_count(text: str) -> int:
    return len(text.split())


def _line_pool(style: str, section: str) -> List[str]:
    return VIDEO_SCRIPT_STYLE_SETTINGS[_normalize_style(style)][section]


def _pick_line(style: str, section: str, used_lines: set[str]) -> str:
    options = [line for line in _line_pool(style, section) if line not in used_lines]
    choice = _pick(options or _line_pool(style, section))
    used_lines.add(choice)
    return choice


def _render_lines(lines: List[str]) -> str:
    return "\n".join(lines)


def _pick_hook(topic: str) -> List[str]:
    hook_style = random.choice(list(HOOK_STYLE_POOLS))
    hook_line = _pick(HOOK_STYLE_POOLS[hook_style]).format(topic=topic)
    hook_line = hook_line[:1].upper() + hook_line[1:] if hook_line else hook_line
    follow_line = random.choice(HOOK_FOLLOW_LINES)
    return [hook_line, follow_line]


def _maybe_pause_lines() -> List[str]:
    pause_count = random.choices([0, 1, 2], weights=[6, 3, 1], k=1)[0]
    if pause_count == 0:
        return []
    return random.sample(PAUSE_LINES, k=pause_count)


def generate_short_video_script(
    topic: str,
    style: str = "balanced",
    db_path: Path = DB_PATH,
) -> str:
    context = get_project_context(topic=topic, db_path=db_path)
    topic_value = str(context["topic"])
    style_value = _normalize_style(style)
    used_lines: set[str] = set()

    hook_lines = _pick_hook(topic_value)

    context_lines = [
        _pick_line(style_value, "context_open", used_lines),
        _pick_line(style_value, "context_build", used_lines),
    ]
    runtime_line = _compose_context_line(context, include_detail=False)
    if context["has_runtime_context"]:
        context_lines.append(runtime_line)
    else:
        context_lines.append("It is still thin, but it is grounded in the real ARI system that is already there.")

    core_lines = [
        _pick_line(style_value, "core_open", used_lines),
        _pick_line(style_value, "core_middle", used_lines),
        random.choice(WHY_LINES),
        _pick_line(style_value, "core_why", used_lines),
    ]
    if style_value == "story":
        core_lines.extend(["That rhythm matters more than perfect wording."])
    elif style_value == "tactical":
        core_lines.extend(["The target is simple.", "Something I can record in about half a minute."])
    elif style_value == "insight":
        core_lines.extend(["That is a design choice.", "Not just a copy choice."])
    else:
        core_lines.extend(["If the script sounds natural,", "the layer is doing its job."])

    core_lines.extend(_maybe_pause_lines())

    close_lines = [
        _pick_line(style_value, "close", used_lines),
        *(_maybe_pause_lines()[:1]),
        random.choice(CREATOR_CLOSE_LINES),
    ]

    sections = {
        "HOOK": hook_lines,
        "CONTEXT": context_lines,
        "CORE IDEA": core_lines,
        "CTA / CLOSE": close_lines,
    }

    trim_order = [
        ("CORE IDEA", 4),
        ("CONTEXT", 2),
        ("HOOK", 1),
        ("CTA / CLOSE", 1),
    ]
    script = "\n\n".join(f"{label}\n{_render_lines(lines)}" for label, lines in sections.items())
    while _word_count(script) > 150:
        trimmed = False
        for label, minimum_length in trim_order:
            lines = sections[label]
            if len(lines) > minimum_length:
                lines.pop()
                trimmed = True
                break
        if not trimmed:
            break
        script = "\n\n".join(f"{label}\n{_render_lines(lines)}" for label, lines in sections.items())
    return script


def generate_linkedin_draft(
    topic: str,
    mode: str = "balanced",
    style: str = "balanced",
    format: str = "full",
    db_path: Path = DB_PATH,
) -> str:
    context = get_project_context(topic=topic, db_path=db_path)
    topic_value = str(context["topic"])
    style_value = _normalize_style(style)
    format_value = format.strip().lower()
    if format_value not in {"full", "short"}:
        raise ValueError(f"Unsupported format: {format}")

    if format_value == "short":
        return _compose_short_format(topic_value, context, mode, style_value)

    lines = [
        f"Hook: {_compose_hook(topic_value, style_value)}",
        f"What I built / learned: {_compose_built_learned_section(topic_value, context, mode, style_value)}",
        f"Why it matters: {_compose_why_it_matters_section(mode, style_value)}",
        f"Forward-looking: {_compose_forward_looking_line(mode, style_value)}",
    ]
    return "\n".join(lines)


def handle_content_linkedin(args: argparse.Namespace, db_path: Path = DB_PATH) -> int:
    mode = _resolve_mode(args)
    draft = generate_linkedin_draft(
        topic=args.topic,
        mode=mode,
        style=getattr(args, "style", "balanced"),
        format=getattr(args, "format", "full"),
        db_path=db_path,
    )
    print(draft)
    if getattr(args, "save", False):
        _save_draft(draft)
    return 0


def handle_script_short_video(args: argparse.Namespace, db_path: Path = DB_PATH) -> int:
    script = generate_short_video_script(
        topic=args.topic,
        style=getattr(args, "style", "balanced"),
        db_path=db_path,
    )
    print(script)
    return 0
