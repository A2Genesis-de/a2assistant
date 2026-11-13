"""Skills Hub adapters for well-known endpoints and direct URLs."""

import hashlib
import json
import logging
import re
from typing import Any, Dict, List, Optional, Union
from urllib.parse import quote, urljoin, urlparse, urlunparse

from tools.skills_hub_models import (
    GuardedFetchMixin, SkillBundle, SkillMeta, SkillSource,
    _hermes_tags, _memo_json, _parse_frontmatter, _referenced_support_paths,
    _validate_bundle_rel_path, _validate_skill_name, hub,
)

logger = logging.getLogger("tools.skills_hub")


# --- Well-known Agent Skills endpoint source adapter ------------------------

class WellKnownSkillSource(GuardedFetchMixin, SkillSource):
    """Read skills from a domain exposing /.well-known/skills/index.json."""

    SOURCE_ID = "well-known"
    BASE_PATH = "/.well-known/skills"

    def _meta(self, parsed: dict, skill_name: str, description: str, files: Any, **extra) -> SkillMeta:
        return SkillMeta(
            name=skill_name, description=description, source="well-known",
            identifier=self._wrap_identifier(parsed["base_url"], skill_name), trust_level="community",
            path=skill_name,
            extra={"index_url": parsed["index_url"], "base_url": parsed["base_url"], "files": files, **extra},
        )

    def search(self, query: str, limit: int = 10) -> list[SkillMeta]:
        index_url = self._query_to_index_url(query)
        parsed = self._parse_index(index_url) if index_url else None
        if not parsed:
            return []
        results: list[SkillMeta] = []
        for entry in parsed["skills"][:limit]:
            name = entry.get("name")
            if not isinstance(name, str) or not name:
                continue
            files = entry.get("files", ["SKILL.md"])
            results.append(self._meta(parsed, name, str(entry.get("description", "")),
                                      files if isinstance(files, list) else ["SKILL.md"]))
        return results

    def inspect(self, identifier: str) -> Optional[SkillMeta]:
        parsed = self._parse_identifier(identifier)
        entry = self._index_entry(parsed["index_url"], parsed["skill_name"]) if parsed else None
        skill_md = self._fetch_text(f"{parsed['skill_url']}/SKILL.md") if entry else None
        if skill_md is None:
            return None
        fm = _parse_frontmatter(skill_md)
        return self._meta(parsed, str(fm.get("name") or parsed["skill_name"]),
                          str(fm.get("description") or entry.get("description") or ""),
                          entry.get("files", ["SKILL.md"]), endpoint=parsed["skill_url"])

    def fetch(self, identifier: str) -> Optional[SkillBundle]:
        parsed = self._parse_identifier(identifier)
        if not parsed:
            return None
        try:
            skill_name = _validate_skill_name(parsed["skill_name"])
        except ValueError:
            logger.warning("Well-known skill identifier contained unsafe skill name: %s", identifier)
            return None
        entry = self._index_entry(parsed["index_url"], parsed["skill_name"])
        if not entry:
            return None
        files = entry.get("files", ["SKILL.md"])
        if not isinstance(files, list) or not files:
            files = ["SKILL.md"]
        downloaded: dict[str, str] = {}
        for rel_path in files:
            if not isinstance(rel_path, str) or not rel_path:
                continue
            try:
                safe_rel_path = _validate_bundle_rel_path(rel_path)
            except ValueError:
                logger.warning("Well-known skill %s advertised unsafe file path: %r", identifier, rel_path)
                return None
            text = self._fetch_text(f"{parsed['skill_url']}/{safe_rel_path}")
            if text is None:
                return None
            downloaded[safe_rel_path] = text
        if "SKILL.md" not in downloaded:
            return None
        return SkillBundle(
            name=skill_name, files=downloaded, source="well-known",
            identifier=self._wrap_identifier(parsed["base_url"], skill_name), trust_level="community",
            metadata={"index_url": parsed["index_url"], "base_url": parsed["base_url"],
                      "endpoint": parsed["skill_url"], "files": files},
        )

    def _query_to_index_url(self, query: str) -> Optional[str]:
        query = query.strip()
        if not query.startswith(("http://", "https://")):
            return None
        if query.endswith("/index.json"):
            return query
        if f"{self.BASE_PATH}/" in query:
            return query.split(f"{self.BASE_PATH}/", 1)[0] + f"{self.BASE_PATH}/index.json"
        return query.rstrip("/") + f"{self.BASE_PATH}/index.json"

    def _parse_identifier(self, identifier: str) -> Optional[dict]:
        raw = identifier.removeprefix("well-known:")
        if not raw.startswith(("http://", "https://")):
            return None
        parsed_url = urlparse(raw)
        clean_url = urlunparse(parsed_url._replace(fragment=""))
        if clean_url.endswith("/index.json"):
            if not parsed_url.fragment:
                return None
            base_url, skill_name = clean_url[:-len("/index.json")], parsed_url.fragment
            skill_url = f"{base_url}/{skill_name}"
        else:
            skill_url = clean_url[:-len("/SKILL.md")] if clean_url.endswith("/SKILL.md") else clean_url.rstrip("/")
            if f"{self.BASE_PATH}/" not in skill_url:
                return None
            base_url, skill_name = skill_url.rsplit("/", 1)
        return {"index_url": f"{base_url}/index.json", "base_url": base_url,
                "skill_name": skill_name, "skill_url": skill_url}

    def _parse_index(self, index_url: str) -> Optional[dict]:
        def compute():
            resp = hub()._guarded_http_get(index_url, timeout=20)
            if resp is None or resp.status_code != 200:
                return None
            try:
                data = resp.json()
            except json.JSONDecodeError:
                return None
            skills = data.get("skills", []) if isinstance(data, dict) else []
            if not isinstance(skills, list):
                return None
            return {"index_url": index_url, "base_url": index_url[:-len("/index.json")], "skills": skills}

        return _memo_json(f"well_known_index_{hashlib.md5(index_url.encode()).hexdigest()}", compute,
                          valid=lambda c: isinstance(c, dict) and isinstance(c.get("skills"), list))

    def _index_entry(self, index_url: str, skill_name: str) -> Optional[dict]:
        parsed = self._parse_index(index_url)
        skills = parsed["skills"] if parsed else []
        return next((e for e in skills if isinstance(e, dict) and e.get("name") == skill_name), None)

    @staticmethod
    def _wrap_identifier(base_url: str, skill_name: str) -> str:
        return f"well-known:{base_url.rstrip('/')}/{skill_name}"


# --- Direct URL source adapter ----------------------------------------------

class UrlSource(GuardedFetchMixin, SkillSource):
    """Fetch SKILL.md plus explicitly referenced, allowlisted support files.

    The identifier IS the URL (``https://example.com/path/SKILL.md``). Bare URLs cannot enumerate a
    repository, so only exact references below references/templates/scripts/assets are fetched. The
    skill name comes from frontmatter ``name:`` (URL-slug fallback); trust is always ``community``.
    """

    SOURCE_ID = "url"
    # Skill names must look like identifiers: lowercase letters/digits with optional hyphens/underscores.
    # Blocks dangerous (``../evil``) AND useless (``SKILL``, ``README``, empty) candidates before they hit the disk.
    _VALID_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]*$")

    def search(self, query: str, limit: int = 10) -> list[SkillMeta]:
        return []  # search is meaningless for a direct URL

    def _matches(self, identifier: str) -> bool:
        """Claim bare HTTP(S) URLs ending in ``.md``; leave wrapped identifiers
        and ``/.well-known/skills/`` URLs to their own adapters."""
        if not isinstance(identifier, str):
            return False
        ident = identifier.strip()
        if (not ident.lower().startswith(("http://", "https://")) or "/.well-known/skills/" in ident
                or ident.rstrip("/").endswith("/index.json")):
            return False
        try:
            return urlparse(ident).path.lower().endswith(".md")
        except ValueError:
            return False

    def _load(self, identifier: str):
        """``(url, text, frontmatter, resolved name)`` for a claimed identifier, else None."""
        if not self._matches(identifier):
            return None
        url = identifier.strip()
        text = self._fetch_text(url)
        if text is None:
            return None
        fm = _parse_frontmatter(text)
        return url, text, fm, self._resolve_skill_name(fm, url)

    def inspect(self, identifier: str) -> Optional[SkillMeta]:
        loaded = self._load(identifier)
        if loaded is None:
            return None
        url, _text, fm, name = loaded
        raw_tags = _hermes_tags(fm)
        return SkillMeta(
            name=name or "", description=str(fm.get("description") or ""), source="url", identifier=url,
            trust_level="community", path=name or "",
            tags=[str(t) for t in raw_tags] if isinstance(raw_tags, list) else [],
            extra={"url": url, "awaiting_name": name is None},
        )

    def fetch(self, identifier: str) -> Optional[SkillBundle]:
        loaded = self._load(identifier)
        if loaded is None:
            return None
        url, text, _fm, name = loaded
        referenced = _referenced_support_paths(text)
        if referenced is None:
            return None
        files: dict[str, str | bytes] = {"SKILL.md": text}
        base_url = url.rsplit("/", 1)[0] + "/"
        for rel_path in sorted(referenced):
            support_url = urljoin(base_url, quote(rel_path, safe="/"))
            if urlparse(support_url).netloc != urlparse(url).netloc:
                return None
            content = self._fetch_bytes(support_url)
            if content is None:  # A 404ing support file shouldn't sink the whole install.
                logger.warning("URL skill %s: referenced support file %r could not be fetched from %s; skipping it",
                               url, rel_path, support_url)
                continue
            files[rel_path] = content
        # When no name resolves, return the bundle with an empty name and ``awaiting_name=True``: ``do_install``
        # prompts on a TTY or refuses non-interactively, without re-downloading after the user picks a name.
        skill_name = ""
        if name is not None:
            try:
                skill_name = _validate_skill_name(name)
            except ValueError:
                logger.warning("URL skill %s produced unsafe skill name: %r", url, name)
                return None
        return SkillBundle(name=skill_name, files=files, source="url", identifier=url, trust_level="community",
                           metadata={"url": url, "source_url": url, "awaiting_name": not skill_name})

    @classmethod
    def _is_valid_skill_name(cls, name: Optional[str]) -> bool:
        if not isinstance(name, str):
            return False
        candidate = name.strip().lower()
        return bool(candidate) and candidate not in {"skill", "readme", "index", "unnamed-skill"} and bool(
            cls._VALID_NAME_RE.match(candidate))

    @classmethod
    def _resolve_skill_name(cls, fm: dict, url: str) -> Optional[str]:
        """Frontmatter ``name:`` when valid, else a URL-slug candidate (``.../<name>/SKILL.md`` -> ``<name>``,
        ``.../<name>.md`` -> ``<name>``). None when nothing usable — the CLI then prompts or refuses rather
        than auto-naming something like ``SKILL``."""
        fm_name = fm.get("name") if isinstance(fm, dict) else None
        if isinstance(fm_name, str) and cls._is_valid_skill_name(fm_name):
            return fm_name.strip()
        try:
            path = urlparse(url).path
        except ValueError:
            return None
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 2 and parts[-1].lower() == "skill.md" and cls._is_valid_skill_name(parts[-2]):
            return parts[-2]
        candidate = re.sub(r"\.md$", "", parts[-1], flags=re.IGNORECASE) if parts else ""
        return candidate if cls._is_valid_skill_name(candidate) else None
