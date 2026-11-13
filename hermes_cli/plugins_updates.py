"""Local plugin provenance verdicts; plugin updates are not fetched from any remote."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from hermes_cli.plugins_provenance import Provenance, ProvenanceClass


@dataclass
class CheckResult:
    name: str
    klass: str
    current: Optional[str] = None
    latest: Optional[str] = None
    update_available: Optional[bool] = None
    needs_fixing: Optional[str] = None
    min_hermes: Optional[str] = None
    reason: str = ""

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "class": self.klass,
            "current": self.current,
            "latest": self.latest,
            "update_available": self.update_available,
            "needs_fixing": self.needs_fixing,
            "min_hermes": self.min_hermes,
            "reason": self.reason,
        }


def check_local_provenance(prov: Provenance) -> CheckResult:
    """Describe an installed plugin's provenance without contacting any remote."""
    result = CheckResult(name=prov.name, klass=prov.klass.value, update_available=False)
    if prov.klass is ProvenanceClass.MANUAL:
        result.reason = "no recorded install source"
        return result
    if prov.klass is ProvenanceClass.DRIFT:
        result.reason = (
            f"provenance drift — the install record names {prov.row.get('source')!r} "
            "but the dir has no .git; reinstall from the recorded source"
        )
        return result
    if prov.klass is ProvenanceClass.SELF_CLONED:
        result.reason = "cloned by hand; reinstall with `hermes plugins install --force` to record its source"
        return result
    row = prov.row or {}
    result.current = row.get("revision") or None
    if row.get("pinned") is True:
        result.reason = f"pinned @ {(result.current or '')[:12] or 'sha'}"
    return result


def parse_feed_yml(text: str) -> dict:
    """The electron-updater-derived feed shape: version, released,
    min_hermes, artifacts{git,bundle,bundle_sha256}, notes_url."""
    import hermes_yaml as yaml

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid feed YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("feed must be a YAML mapping")
    version = data.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("feed missing 'version'")
    out: dict[str, Any] = {"version": version.strip()}
    for key in ("min_hermes", "notes_url"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            out[key] = value.strip()
    artifacts = data.get("artifacts")
    if isinstance(artifacts, dict):
        git = artifacts.get("git")
        if git is not None and not isinstance(git, str):
            raise ValueError("feed artifacts.git must be a string")
        out["artifacts"] = {
            k: v for k, v in artifacts.items() if isinstance(v, str)
        }
    return out


def default_fetch(url: str) -> str:
    raise OSError("plugin update feeds are not fetched")
