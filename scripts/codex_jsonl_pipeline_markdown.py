from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

TURN_SECTION = "## Turn-by-Turn Analysis"
OVERALL_SECTION = "## Overall Findings"
FILE_INFO_SECTION = "## File Information"
REPORT_TITLE_PREFIX = "# Conversation Audit Report:"
TURN_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "User Request Analysis": ("\u7528\u6237\u8bc9\u6c42\u6df1\u5ea6\u5206\u6790",),
    "User Tone And Attitude": ("\u7528\u6237\u60c5\u7eea\u4e0e\u6001\u5ea6",),
    "Codex Response Analysis": ("Codex \u54cd\u5e94\u6df1\u5ea6\u5206\u6790",),
    "Next Action Suggestion": ("\u540e\u7eed\u884c\u52a8\u5efa\u8bae",),
    "Interaction Efficiency": ("\u4ea4\u4e92\u6548\u7387\u8bc4\u4f30",),
}

PROMPT_TEMPLATE = """
# Role: Conversation Auditor

You will produce a turn-by-turn audit markdown document from the supplied turn data.

[Facts Only]
- Use only the provided JSON turn data.
- Do not invent code changes, terminal commands, or tool calls.
- If evidence is insufficient, write "Insufficient evidence".

[Goals]
For each turn, extract:
1) What the user asked for (object + action + constraints)
2) The user's tone (labels + strength + evidence)
3) What Codex actually did or said (including whether it truly executed)
4) The next-step suggestion (present/absent + action items)
5) Interaction efficiency (did the turn move the task forward?)

[Hard Output Rules]
- The markdown must contain `## Turn-by-Turn Analysis` and `## Overall Findings`.
- Each turn must use `### Turn <turn_id>`.
- Each turn must contain these five level-4 headings:
  - `#### User Request Analysis`
  - `#### User Tone And Attitude`
  - `#### Codex Response Analysis`
  - `#### Next Action Suggestion`
  - `#### Interaction Efficiency`
- Cover every turn, in order, with no omissions or duplicates.

[Writing Guidance]
- Keep each level-4 section to 3-6 concise bullets.
- Prioritize verifiable facts plus short explanations.
- Do not paste long original passages; summarize only the important fragments.

[Output Format]
# Conversation Audit Report: {title}

## File Information
- Source file: `{relative_path}`
- Total turns: <number>
- Generated at: <YYYY-MM-DD HH:MM:SS>
- Overall satisfaction trend: <one sentence>

## Turn-by-Turn Analysis
### Turn <turn_id>
#### User Request Analysis
- ...
#### User Tone And Attitude
- ...
#### Codex Response Analysis
- ...
#### Next Action Suggestion
- ...
#### Interaction Efficiency
- ...

## Overall Findings
- Key blockers: ...
- Interaction quality score: ...
- Next-step recommendation: ...

Output only the markdown body. Do not include process notes.
"""

REQUIRED_TURN_FIELDS: tuple[str, ...] = (
    "User Request Analysis",
    "User Tone And Attitude",
    "Codex Response Analysis",
    "Next Action Suggestion",
    "Interaction Efficiency",
)
TURN_HEADER_PATTERN = re.compile(r"^###\s+Turn\s+(.+?)\s*$", flags=re.MULTILINE)

PATH_PROMPT_TEMPLATE = """
# Role: Conversation Auditor

You need to audit a local JSONL file and output the final markdown result.

[Source File]
- Title: `{title}`
- Relative path: `{relative_path}`
- Absolute path: `{absolute_path}`
- Expected turn count: {turn_count}

[Mandatory Read Rules]
- Read the local file in batches as needed (20-50 turns per batch).
- Analyze only records where `type == "turn"`.
- Do not dump the whole JSONL into context at once.

[Forbidden Output]
- "I will continue reading..."
- "I will process this in batches..."
- "I will start with batch X..."

You only get one final response. Output the complete markdown directly.

[Turn Order Constraint]
```json
{turn_id_order_json}
```

[Hard Output Rules]
- The markdown must contain `## Turn-by-Turn Analysis` and `## Overall Findings`.
- Each turn title must be `### Turn <turn_id>`.
- Each turn must contain these five level-4 headings:
  - `#### User Request Analysis`
  - `#### User Tone And Attitude`
  - `#### Codex Response Analysis`
  - `#### Next Action Suggestion`
  - `#### Interaction Efficiency`
- Cover all turns in the exact expected order.

Output only the final markdown body.
"""

CHUNK_PROMPT_TEMPLATE = """
# Role: Conversation Auditor

You are processing a chunked subset of turns from one file. Output only the turn analysis for this chunk and do not include process notes.

[Source File]
- Title: `{title}`
- Relative path: `{relative_path}`
- Absolute path: `{absolute_path}`
- Chunk: {chunk_index}/{chunk_total}

[Required Turn Order For This Chunk]
```json
{chunk_turn_ids_json}
```

[Input Data For This Chunk]
```json
{chunk_payload_json}
```

[Hard Output Rules]
- Output must contain `## Turn-by-Turn Analysis`.
- Each turn title must be `### Turn <turn_id>`.
- Each turn must contain these five level-4 headings:
  - `#### User Request Analysis`
  - `#### User Tone And Attitude`
  - `#### Codex Response Analysis`
  - `#### Next Action Suggestion`
  - `#### Interaction Efficiency`
- Cover exactly the turn IDs in this chunk, in order, with no omissions or duplicates.
- Do not output `## Overall Findings`, file information, or "I am processing batch X".

Output only markdown.
"""


def _now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def trim_text(value: object, max_chars: int) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[:max_chars] + "...[truncated]"


def _normalize_turn_id(raw_turn_id: object, fallback_index: int) -> str:
    if raw_turn_id is None:
        return str(fallback_index)
    text = str(raw_turn_id).strip()
    return text if text else str(fallback_index)


def load_compact_turns(
    jsonl_path: Path,
    max_chars_per_side: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str], int]:
    manifest: dict[str, Any] = {}
    turns: list[dict[str, Any]] = []
    turn_ids: list[str] = []
    bad_line_count = 0

    with jsonl_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                bad_line_count += 1
                continue

            rec_type = obj.get("type")
            if rec_type == "manifest":
                manifest = {
                    "session_id": obj.get("session_id"),
                    "session_timestamp": obj.get("session_timestamp"),
                    "workspace_cwd": obj.get("workspace_cwd"),
                    "turn_count": obj.get("turn_count"),
                }
                continue

            if rec_type != "turn":
                continue

            turn_id = _normalize_turn_id(obj.get("turn_id"), len(turns) + 1)
            turn_ids.append(turn_id)
            turns.append(
                {
                    "turn_id": turn_id,
                    "start_ts": obj.get("start_ts"),
                    "end_ts": obj.get("end_ts"),
                    "user_prompt": trim_text(obj.get("user_prompt"), max_chars_per_side),
                    "assistant_reply": trim_text(obj.get("assistant_reply"), max_chars_per_side),
                    "code_changes_count": len(obj.get("code_changes") or []),
                    "tool_calls_count": len(obj.get("tool_calls") or []),
                    "terminal_commands_count": len(obj.get("terminal_commands") or []),
                }
            )

    return manifest, turns, turn_ids, bad_line_count


def build_turn_index(jsonl_path: Path) -> tuple[dict[str, Any], list[str], int]:
    manifest, _, turn_ids, bad_line_count = load_compact_turns(jsonl_path, max_chars_per_side=0)
    return manifest, turn_ids, bad_line_count


def build_embedded_turn_payload(jsonl_path: Path, max_chars_per_side: int) -> tuple[dict[str, Any], list[str], int]:
    manifest, turns, turn_ids, bad_line_count = load_compact_turns(jsonl_path, max_chars_per_side)
    payload = {
        "manifest": manifest,
        "turn_id_order": turn_ids,
        "turns": turns,
    }
    return payload, turn_ids, bad_line_count


def split_turn_chunks(turns: list[dict[str, Any]], chunk_size: int) -> list[list[dict[str, Any]]]:
    size = max(1, chunk_size)
    return [turns[index : index + size] for index in range(0, len(turns), size)]


def _resolve_codex_prompt_mode(args: argparse.Namespace, turn_count: int) -> str:
    if args.provider != "codex":
        return "embedded"
    if args.codex_prompt_mode in {"embedded", "path", "chunked"}:
        return args.codex_prompt_mode

    if turn_count >= max(1, args.codex_chunk_threshold_turns):
        return "chunked"
    if turn_count >= max(1, args.codex_path_threshold_turns):
        return "path"
    return "embedded"


def build_prompt(
    jsonl_path: Path,
    root: Path,
    args: argparse.Namespace,
) -> tuple[str, list[str], int, str]:
    title = f"{jsonl_path.stem} - turn-by-turn audit"
    relative_path = jsonl_path.relative_to(root)

    _, turn_ids, bad_line_count = build_turn_index(jsonl_path)
    prompt_mode = _resolve_codex_prompt_mode(args, len(turn_ids))

    if prompt_mode == "chunked":
        return "", turn_ids, bad_line_count, prompt_mode

    if prompt_mode == "path":
        prompt = PATH_PROMPT_TEMPLATE.format(
            title=title,
            relative_path=str(relative_path),
            absolute_path=str(jsonl_path),
            turn_count=len(turn_ids),
            turn_id_order_json=json.dumps(turn_ids, ensure_ascii=False),
        )
        return prompt, turn_ids, bad_line_count, prompt_mode

    payload, expected_turn_ids, bad_line_count = build_embedded_turn_payload(jsonl_path, args.max_chars_per_side)
    payload_json = json.dumps(payload, ensure_ascii=False)
    prompt = (
        PROMPT_TEMPLATE.format(title=title, relative_path=str(relative_path))
        + "\n\n[Input turn data (must cover every turn_id)]\n"
        + "```json\n"
        + payload_json
        + "\n```\n"
    )
    return prompt, expected_turn_ids, bad_line_count, prompt_mode


def build_chunk_prompt(
    *,
    jsonl_path: Path,
    root: Path,
    chunk_turns: list[dict[str, Any]],
    chunk_turn_ids: list[str],
    chunk_index: int,
    chunk_total: int,
) -> str:
    title = f"{jsonl_path.stem} - turn-by-turn audit"
    relative_path = jsonl_path.relative_to(root)
    chunk_payload_json = json.dumps(
        {
            "chunk_turn_id_order": chunk_turn_ids,
            "turns": chunk_turns,
        },
        ensure_ascii=False,
    )
    return CHUNK_PROMPT_TEMPLATE.format(
        title=title,
        relative_path=str(relative_path),
        absolute_path=str(jsonl_path),
        chunk_index=chunk_index,
        chunk_total=chunk_total,
        chunk_turn_ids_json=json.dumps(chunk_turn_ids, ensure_ascii=False),
        chunk_payload_json=chunk_payload_json,
    )


def compose_chunked_markdown(
    *,
    jsonl_path: Path,
    root: Path,
    expected_turn_ids: list[str],
    turn_sections: dict[str, str],
) -> str:
    relative_path = jsonl_path.relative_to(root)
    lines = [
        f"{REPORT_TITLE_PREFIX} {jsonl_path.stem} - turn-by-turn audit",
        "",
        FILE_INFO_SECTION,
        f"- Source file: `{relative_path}`",
        f"- Total turns: {len(expected_turn_ids)}",
        f"- Generated at: {_now_ts()}",
        "- Overall satisfaction trend: derive from the per-turn analysis (chunk-merged output).",
        "",
        TURN_SECTION,
    ]

    for turn_id in expected_turn_ids:
        body = turn_sections.get(turn_id, "").strip()
        lines.append(f"### Turn {turn_id}")
        if body:
            lines.append(body)
        lines.append("")

    lines.extend(
        [
            OVERALL_SECTION,
            "- Key blockers: summarize them from the per-turn interaction-efficiency and next-action sections.",
            "- Interaction quality score: derive it from user-tone shifts and execution hit-rate.",
            "- Next-step recommendation: prioritize the most frequently blocked turns and close them one by one.",
            "",
        ]
    )
    return "\n".join(lines)


def persist_invalid_markdown(md_path: Path, attempt: int) -> str:
    if not md_path.exists():
        return ""
    text = md_path.read_text(encoding="utf-8")
    if not text.strip():
        return ""

    invalid_path = md_path.with_suffix(md_path.suffix + f".attempt{attempt}.invalid")
    invalid_path.write_text(text, encoding="utf-8")
    return str(invalid_path)


def _extract_turn_sections(md_text: str) -> tuple[list[str], dict[str, str]]:
    matches = list(TURN_HEADER_PATTERN.finditer(md_text))
    turn_ids: list[str] = []
    sections: dict[str, str] = {}

    for index, match in enumerate(matches):
        turn_id = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(md_text)
        turn_ids.append(turn_id)
        sections[turn_id] = md_text[start:end]

    return turn_ids, sections


def validate_markdown_text(
    md_text: str,
    expected_turn_ids: list[str],
    *,
    require_overall_section: bool,
) -> tuple[bool, str, dict[str, str]]:
    text = md_text.strip()
    if not text:
        return False, "markdown empty", {}

    has_turn_section = TURN_SECTION in text or "## \u8f6e\u6b21\u63d0\u70bc" in text
    if not has_turn_section:
        return False, "missing section: turn-by-turn analysis", {}
    has_overall_section = OVERALL_SECTION in text or "## \u603b\u4f53\u89c2\u5bdf" in text
    if require_overall_section and not has_overall_section:
        return False, "missing section: overall findings", {}

    text_for_turns = text
    if not require_overall_section:
        if OVERALL_SECTION in text_for_turns:
            text_for_turns = text_for_turns.split(OVERALL_SECTION, 1)[0].rstrip()
        elif "## \u603b\u4f53\u89c2\u5bdf" in text_for_turns:
            text_for_turns = text_for_turns.split("## \u603b\u4f53\u89c2\u5bdf", 1)[0].rstrip()

    parsed_turn_ids, sections = _extract_turn_sections(text_for_turns)
    if expected_turn_ids:
        if not parsed_turn_ids:
            return False, "no turn sections", {}
        if len(parsed_turn_ids) != len(set(parsed_turn_ids)):
            return False, "duplicate turn sections", {}
        if parsed_turn_ids != expected_turn_ids:
            return (
                False,
                f"turn order/id mismatch expected={expected_turn_ids} actual={parsed_turn_ids}",
                sections,
            )

        for turn_id in expected_turn_ids:
            section_body = sections.get(turn_id, "")
            for field in REQUIRED_TURN_FIELDS:
                aliases = TURN_FIELD_ALIASES.get(field, ())
                candidate_headings = (field, *aliases)
                if not any(
                    re.search(rf"(?m)^####\s+{re.escape(candidate)}", section_body) is not None
                    for candidate in candidate_headings
                ):
                    return False, f"turn {turn_id} missing field: {field}", sections
    elif parsed_turn_ids:
        return False, "unexpected turn sections for zero-turn input", {}

    return True, "ok", sections


def markdown_is_valid(md_path: Path, expected_turn_ids: list[str]) -> tuple[bool, str]:
    if not md_path.exists():
        return False, "markdown not created"

    text = md_path.read_text(encoding="utf-8")
    valid, reason, _ = validate_markdown_text(
        text,
        expected_turn_ids,
        require_overall_section=True,
    )
    return valid, reason
