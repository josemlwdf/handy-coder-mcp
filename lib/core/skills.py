"""Skill library tool: list, read, and save reusable skill documents.

Skills are Markdown files with a small frontmatter block::

    ---
    name: my-skill
    description: One-line summary of when to use the skill.
    invokable: true
    ---

    Body of the skill...

They live in ``skills/<name>/SKILL.md`` (override the base directory with
``HANDY_CODER_SKILLS_DIR``).
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from ..support import describe

SKILLS_DIR_ENV: str = "HANDY_CODER_SKILLS_DIR"
DEFAULT_SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"
BASELINE_SKILLS = frozenset(
    {"grill-me", "handoff", "mcp-audit", "mcp-tools-only", "plan", "troubleshoot"}
)
BASELINE_SKILLS_INLINE = ", ".join(sorted(BASELINE_SKILLS))
MAX_SKILL_BYTES = 256 * 1024
MAX_DESCRIPTION_CHARS: int = 300
SKILL_FILE_NAME: str = "SKILL.md"
REFERENCES_DIR_NAME: str = "references"
REFERENCE_FILE_EXTENSION: str = ".md"
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def _skills_dir() -> Path:
    """Skills dir function."""
    override = os.environ.get(SKILLS_DIR_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return DEFAULT_SKILLS_DIR


def _skill_dir(name: str) -> Path:
    """Skill dir function."""
    return _skills_dir() / name


def _skill_file(name: str) -> Path:
    """Skill file function."""
    return _skill_dir(name) / SKILL_FILE_NAME


def _reference_dir(name: str) -> Path:
    """Reference dir function."""
    return _skill_dir(name) / REFERENCES_DIR_NAME


def _reference_file(name: str, reference: str) -> Path:
    """Reference file function."""
    return _reference_dir(name) / f"{reference}{REFERENCE_FILE_EXTENSION}"


def _is_within(base: Path, candidate: Path) -> bool:
    """Return True when candidate resolves to base or one of its descendants."""
    try:
        base_resolved = base.resolve()
        candidate_resolved = candidate.resolve(strict=False)
    except OSError:
        return False
    return (
        candidate_resolved == base_resolved
        or base_resolved in candidate_resolved.parents
    )


def _error(code: str, message: str, **extra) -> dict:
    """Error function."""
    return {"error_code": code, "message": message, **extra}


def _parse(text: str) -> tuple[dict[str, str], str]:
    """Split a skill document into (frontmatter metadata, body)."""
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return {}, text
    lines = text.split("\n")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            meta: dict[str, str] = {}
            for line in lines[1:index]:
                key, sep, value = line.partition(":")
                if sep and key.strip():
                    meta[key.strip().lower()] = value.strip()
            return meta, "\n".join(lines[index + 1 :]).lstrip("\n")
    return {}, text


def _validate_name(name: str | None) -> dict | None:
    """Validate name function."""
    if not name:
        return _error("missing_argument", "name is required for this action")
    if not _NAME_RE.match(name):
        return _error(
            "invalid_name",
            "Skill name must be 1-64 chars of lowercase letters, digits and hyphens, "
            "starting with a letter or digit.",
        )
    return None


def _validate_reference_name(reference: str | None) -> dict | None:
    """Validate reference name function."""
    if not reference:
        return _error(
            "missing_argument", "reference is required for this action"
        )
    if not _NAME_RE.match(reference):
        return _error(
            "invalid_reference_name",
            "Reference name must be 1-64 chars of lowercase letters, digits and hyphens, "
            "starting with a letter or digit.",
        )
    return None


def _entry(name: str, text: str) -> dict:
    """Entry function."""
    meta, _ = _parse(text)
    return {
        "name": name,
        "description": meta.get("description", ""),
        "invokable": meta.get("invokable", "true").lower() == "true",
        "tags": [tag.strip() for tag in meta.get("tags", "").split(",") if tag.strip()],
        "version": meta.get("version", "1"),
    }


def _list_skills() -> dict:
    """List skills function."""
    directory = _skills_dir()
    skills: list[dict] = []
    errors: list[dict] = []
    if directory.is_dir():
        for skill_dir in sorted(path for path in directory.iterdir() if path.is_dir()):
            if not _NAME_RE.match(skill_dir.name):
                continue
            path = skill_dir / SKILL_FILE_NAME
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                errors.append(
                    _error(
                        "binary_file",
                        f"Skill file is not valid UTF-8: {skill_dir.name}/{SKILL_FILE_NAME}",
                        name=skill_dir.name,
                    )
                )
                continue
            except OSError as exc:
                errors.append(
                    _error(
                        "io_error",
                        f"{exc.strerror or 'Read failed'}: {skill_dir.name}/{SKILL_FILE_NAME}",
                        name=skill_dir.name,
                    )
                )
                continue
            skills.append(_entry(skill_dir.name, text))
    return {"skills": skills, "count": len(skills), "errors": errors}


def _get_skill(name: str | None) -> dict:
    """Get skill function."""
    problem = _validate_name(name)
    if problem:
        return problem
    path = _skill_file(name)
    if not path.is_file():
        return _error("not_found", f"Skill not found: {name}")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return _error("binary_file", f"Skill file is not valid UTF-8: {name}")
    except OSError as exc:
        return _error("io_error", f"{exc.strerror or 'Read failed'}: {name}")
    _, body = _parse(text)
    return {**_entry(name, text), "content": text, "body": body}


def _list_skill_references(name: str | None) -> dict:
    """List skill references function."""
    problem = _validate_name(name)
    if problem:
        return problem
    skill_path = _skill_file(name)
    if not skill_path.is_file():
        return _error("not_found", f"Skill not found: {name}")
    references_dir = _reference_dir(name)
    references: list[dict[str, str]] = []
    if references_dir.is_dir():
        for item in sorted(references_dir.iterdir()):
            if not item.is_file() or item.suffix.lower() != REFERENCE_FILE_EXTENSION:
                continue
            if not _NAME_RE.match(item.stem):
                continue
            references.append({"name": item.stem, "file": item.name})
    return {"name": name, "references": references, "count": len(references)}


def _get_skill_reference(name: str | None, reference: str | None) -> dict:
    """Get skill reference function."""
    problem = _validate_name(name)
    if problem:
        return problem
    reference_problem = _validate_reference_name(reference)
    if reference_problem:
        return reference_problem
    skill_path = _skill_file(name)
    if not skill_path.is_file():
        return _error("not_found", f"Skill not found: {name}")
    path = _reference_file(name, reference)
    if not path.is_file():
        return _error("not_found", f"Reference not found: {name}/{reference}")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return _error(
            "binary_file", f"Reference file is not valid UTF-8: {name}/{reference}"
        )
    except OSError as exc:
        return _error(
            "io_error", f"{exc.strerror or 'Read failed'}: {name}/{reference}"
        )
    return {"name": name, "reference": reference, "file": path.name, "content": text}


def _save_skill(
    name: str | None,
    description: str | None,
    content: str | None,
    invokable: bool,
    overwrite: bool,
    tags: list[str] | None = None,
    version: str = "1",
) -> dict:
    """Save skill function."""
    problem = _validate_name(name)
    if problem:
        return problem
    if not description or not description.strip():
        return _error("missing_argument", "description is required for save")
    description = description.strip()
    if "\n" in description or "\r" in description:
        return _error("invalid_description", "description must be a single line")
    if len(description) > MAX_DESCRIPTION_CHARS:
        return _error(
            "invalid_description",
            f"description exceeds {MAX_DESCRIPTION_CHARS} characters",
        )
    if not content or not content.strip():
        return _error("missing_argument", "content is required for save")
    body = content.replace("\r\n", "\n").strip("\n")
    if body.startswith("---\n") or body.strip() == "---":
        return _error(
            "content_has_frontmatter",
            "content must be the skill body only; frontmatter is generated from name, description and invokable.",
        )

    document = (
        f"---\nname: {name}\ndescription: {description}\n"
        f"invokable: {'true' if invokable else 'false'}\nversion: {version}\ntags: {','.join(tags or [])}\n---\n\n{body}\n"
    )
    encoded = document.encode("utf-8")
    if len(encoded) > MAX_SKILL_BYTES:
        return _error(
            "skill_too_large", f"Skill exceeds {MAX_SKILL_BYTES // 1024} KiB limit"
        )

    directory = _skills_dir()
    skill_dir = _skill_dir(name)
    path = _skill_file(name)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        if skill_dir.exists() and not skill_dir.is_dir():
            return _error("io_error", f"Skill path is not a directory: {name}")
        skill_dir.mkdir(parents=False, exist_ok=True)
        existed = path.exists()
        if existed and not overwrite:
            return _error(
                "already_exists",
                f"Skill already exists: {name}. Pass overwrite=true to replace it.",
            )
        if overwrite:
            # Atomic replace: write a temp file in the same directory, then swap it in.
            fd, tmp_name = tempfile.mkstemp(
                dir=skill_dir, prefix=f".{name}.", suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(encoded)
                os.replace(tmp_name, path)
            except BaseException:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
                raise
        else:
            # Exclusive create guards against a concurrent save of the same name.
            with open(path, "xb") as handle:
                handle.write(encoded)
    except FileExistsError:
        return _error(
            "already_exists",
            f"Skill already exists: {name}. Pass overwrite=true to replace it.",
        )
    except OSError as exc:
        return _error("io_error", f"{exc.strerror or 'Write failed'}: {name}")
    return {"saved": True, "name": name, "created": not existed, "bytes": len(encoded)}


def skills_manage(
    action: Annotated[
        Literal[
            "list",
            "get",
            "save",
            "search",
            "delete",
            "export",
            "list_references",
            "get_reference",
        ],
        Field(
            description=f"list: return skills (built-in defaults: {BASELINE_SKILLS_INLINE}). search: filter by query. get/export: retrieve full skill Markdown. list_references: list Markdown references for a skill from references/. get_reference: read one reference Markdown file. save: create/update with optional tags and version. delete: remove a skill."
        ),
    ],
    name: Annotated[
        str | None,
        Field(
            description="Skill identifier: lowercase letters, digits and hyphens, max 64 chars. Required for get, export, save, delete, list_references, and get_reference."
        ),
    ] = None,
    description: Annotated[
        str | None,
        Field(
            description="Single-line summary of what the skill does and when to use it. Required for save."
        ),
    ] = None,
    content: Annotated[
        str | None,
        Field(
            description="Skill body in Markdown, without frontmatter (it is generated). Required for save."
        ),
    ] = None,
    invokable: Annotated[
        bool,
        Field(
            description="For save: whether the skill can be invoked directly by the user. Defaults to true."
        ),
    ] = True,
    overwrite: Annotated[
        bool,
        Field(
            description="For save: replace an existing skill with the same name. Defaults to false."
        ),
    ] = False,
    query: Annotated[
        str | None, Field(description="Search text used by the search action.")
    ] = None,
    reference: Annotated[
        str | None,
        Field(
            description="Reference identifier used by get_reference; maps to skills/<name>/references/<reference>.md."
        ),
    ] = None,
    tags: Annotated[
        list[str] | None,
        Field(
            description='Optional array of tag strings stored in skill metadata when saving, for example ["python", "testing"].'
        ),
    ] = None,
    version: Annotated[
        str, Field(description="Skill metadata version, defaults to 1.")
    ] = "1",
    confirm: Annotated[
        bool,
        Field(
            description="For delete: must be true to remove the skill; a backup is kept beside it."
        ),
    ] = False,
) -> dict:
    """Skills manage function."""
    if action == "list":
        return _list_skills()
    if action == "get":
        return _get_skill(name)
    if action == "export":
        return _get_skill(name)
    if action == "list_references":
        return _list_skill_references(name)
    if action == "get_reference":
        return _get_skill_reference(name, reference)
    if action == "search":
        needle = (query or "").lower()
        listed = _list_skills()
        listed["skills"] = [
            s
            for s in listed["skills"]
            if needle in s["name"].lower()
            or needle in s["description"].lower()
            or any(needle in t.lower() for t in s["tags"])
        ]
        listed["count"] = len(listed["skills"])
        return listed
    if action == "delete":
        problem = _validate_name(name)
        if problem:
            return problem
        if name in BASELINE_SKILLS:
            return _error(
                "protected_skill", f"Baseline skill cannot be deleted: {name}"
            )
        if not confirm:
            return _error(
                "confirmation_required",
                f"Call again with confirm=true to delete skill: {name}",
            )
        try:
            directory = _skills_dir()
            path = _skill_file(name)
            skill_dir = path.parent
            if not path.is_file():
                return _error("not_found", f"Skill not found: {name}")
            if skill_dir.is_symlink() or path.is_symlink():
                return _error(
                    "path_escape", f"Skill path escapes the skills directory: {name}"
                )
            if not _is_within(directory, path):
                return _error(
                    "path_escape", f"Skill path escapes the skills directory: {name}"
                )
            backup = path.with_suffix(path.suffix + ".bak")
            if backup.exists():
                return _error(
                    "backup_exists",
                    f"Refusing to overwrite existing backup: {backup.name}",
                )
            if backup.is_symlink() or not _is_within(directory, backup):
                return _error(
                    "path_escape",
                    f"Skill backup path escapes the skills directory: {name}",
                )
            import shutil

            shutil.copy2(path, backup)
            path.unlink()
            try:
                skill_dir.rmdir()
            except OSError:
                pass
            return {"deleted": True, "name": name}
        except FileNotFoundError:
            return _error("not_found", f"Skill not found: {name}")
        except OSError as exc:
            return _error("io_error", f"{exc.strerror or 'Delete failed'}: {name}")
    if action == "save":
        if name in BASELINE_SKILLS:
            return _error(
                "protected_skill", f"Baseline skill cannot be replaced: {name}"
            )
        # Metadata values are plain single-line strings in the simple frontmatter format.
        if not version.strip() or any(c in version for c in "\r\n:"):
            return _error(
                "invalid_version",
                "version must be a non-empty single-line value without ':'",
            )
        if tags and any(
            not tag.strip() or any(c in tag for c in ",\r\n") for tag in tags
        ):
            return _error(
                "invalid_tags",
                "tags must be non-empty single-line values without commas",
            )
        return _save_skill(
            name, description, content, invokable, overwrite, tags, version
        )
    return _error("invalid_action", f"Unknown action: {action}")


def _default_skill_catalog() -> str:
    """Return baseline/default skills with descriptions from the built-in skills directory."""
    lines: list[str] = []
    for name in sorted(BASELINE_SKILLS):
        path = DEFAULT_SKILLS_DIR / name / SKILL_FILE_NAME
        description: str = "(description unavailable)"
        try:
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                description = _entry(name, text)["description"] or description
        except (OSError, UnicodeDecodeError):
            pass
        lines.append(f"- {name}: {description}")
    return "\n".join(lines)


def register(mcp):
    """Register function."""
    baseline_catalog = _default_skill_catalog()
    listed = _list_skills()
    skill_lines: list = [
        f"- {item['name']}: {item['description']}" for item in listed["skills"]
    ]
    skill_catalog = (
        "\n".join(skill_lines)
        if skill_lines
        else "(No skills are currently installed.)"
    )
    return mcp.tool(
        description=describe(
            f"Manage reusable skills stored as Markdown files at skills/<name>/SKILL.md (built-in defaults: {BASELINE_SKILLS_INLINE}). "
            "Default baseline skills and descriptions:\n"
            f"{baseline_catalog}\n"
            "Installed skills and their descriptions at server startup:\n"
            f"{skill_catalog}\n"
            "Actions: list returns name, description, invokable, tags and version; search filters those fields; get/export returns full Markdown; list_references lists available files from skills/<name>/references/*.md; get_reference reads one reference file by reference name; delete requires confirm=true, protects baseline skills, and keeps a .bak backup; "
            'save creates a skill from name, description and content (optional tags as an array of strings, for example ["python", "testing"], and version; fails with already_exists '
            "unless overwrite=true). Failures return error_code (missing_argument, invalid_name, invalid_reference_name, "
            "invalid_description, content_has_frontmatter, skill_too_large, not_found, already_exists, "
            "io_error, confirmation_required, protected_skill, backup_exists, path_escape, binary_file). "
            "Baseline skills (including troubleshoot) cannot be deleted or replaced. "
            "When to use: Discover, load, or record skills that guide how to perform a task."
        )
    )(skills_manage)
