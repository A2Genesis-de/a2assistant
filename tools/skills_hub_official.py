"""Skills Hub official source: the repo-shipped optional skills."""

from pathlib import Path
from typing import Optional

from agent.skill_utils import is_excluded_skill_path
from tools.skills_hub_github import _skip_bundle_file
from tools.skills_hub_models import SkillBundle, SkillMeta, SkillSource, _hermes_tags, _matches_query, _parse_frontmatter


class OptionalSkillSource(SkillSource):
    """Skills from the repo's ``optional-skills/`` directory: official but not activated by
    default — absent from the system prompt and not copied to ~/.hermes/skills/ at setup.
    Discoverable via the Skills Hub as source "official" with "builtin" trust."""

    SOURCE_ID = "official"
    TRUST_LEVEL = "builtin"
    OFFICIAL_REPO = "A2Genesis-de/a2assistant"
    OPTIONAL_SKILLS_PREFIX = "optional-skills"

    _parse_frontmatter = staticmethod(_parse_frontmatter)

    def __init__(self):
        from hermes_constants import get_optional_skills_dir

        self._optional_dir = get_optional_skills_dir(Path(__file__).parent.parent / "optional-skills")

    @staticmethod
    def _rel(identifier: str) -> str:
        return identifier.split("/", 1)[-1] if identifier.startswith("official/") else identifier

    def _meta(self, rel_dir: str, name: str, description: str, tags: list) -> SkillMeta:
        return SkillMeta(
            name=name, description=description, source="official", identifier=f"official/{rel_dir}",
            trust_level="builtin", repo=self.OFFICIAL_REPO,
            path=f"{self.OPTIONAL_SKILLS_PREFIX}/{rel_dir}", tags=tags,
        )

    @staticmethod
    def _bundle(rel_id: str, files: dict[str, str | bytes], **kwargs) -> SkillBundle:
        return SkillBundle(name=rel_id.rsplit("/", 1)[-1], files=files, source="official",
                           identifier=f"official/{rel_id}", trust_level="builtin", **kwargs)

    def search(self, query: str, limit: int = 10) -> list[SkillMeta]:
        results: list[SkillMeta] = []
        query_lower = query.lower()
        for meta in self._scan_all():
            if _matches_query(query_lower, meta.name, meta.description, meta.tags):
                results.append(meta)
            if len(results) >= limit:
                break
        return results

    def fetch(self, identifier: str) -> Optional[SkillBundle]:
        rel = self._rel(identifier)
        try:
            resolved = (self._optional_dir / rel).resolve()
            optional_root = self._optional_dir.resolve()
            if not resolved.is_relative_to(optional_root):
                return None
        except (OSError, ValueError):
            return None
        skill_dir = resolved if resolved.is_dir() else self._find_skill_dir(rel.rsplit("/", 1)[-1])
        if not skill_dir:
            return None
        rel_id = skill_dir.resolve().relative_to(optional_root).as_posix()
        files: dict[str, str | bytes] = {}
        for f in skill_dir.rglob("*"):
            if f.is_file() and not _skip_bundle_file(f.relative_to(skill_dir).as_posix()):
                try:
                    files[str(f.relative_to(skill_dir))] = f.read_bytes()
                except OSError:
                    continue
        return self._bundle(rel_id, files) if files else None

    def inspect(self, identifier: str) -> Optional[SkillMeta]:
        skill_name = self._rel(identifier).rsplit("/", 1)[-1]
        return next((meta for meta in self._scan_all() if meta.name == skill_name), None)

    def list_local(self) -> list[SkillMeta]:
        """Every optional skill in the local checkout, with frontmatter metadata
        (backs the dashboard/desktop "built-in optional skills" catalog)."""
        return self._scan_all()

    def _local_skill_mds(self):
        root = self._optional_dir
        return (md for md in (sorted(root.rglob("SKILL.md")) if root.is_dir() else [])
                if not is_excluded_skill_path(md.relative_to(root), root=root))

    def _find_skill_dir(self, name: str) -> Optional[Path]:
        """Find a skill directory by name anywhere in optional-skills/."""
        return next((md.parent for md in self._local_skill_mds() if md.parent.name == name), None)

    def _scan_all(self) -> list[SkillMeta]:
        """Enumerate all optional skills with metadata."""
        results: list[SkillMeta] = []
        for skill_md in self._local_skill_mds():
            parent = skill_md.parent
            try:
                content = skill_md.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError):
                continue
            fm = _parse_frontmatter(content)
            tags = _hermes_tags(fm)
            results.append(self._meta(parent.relative_to(self._optional_dir).as_posix(), fm.get("name", parent.name),
                                      fm.get("description", "")[:200], tags if isinstance(tags, list) else []))
        return results
