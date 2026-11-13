"""Driver-agnostic out-of-band notice (``AIAgent.notice_callback`` / ``notice_clear_callback``).

Each driver renders it its own way; ``kind`` is ``sticky`` or ``ttl`` (``ttl_ms`` honored only then).
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class AgentNotice:
    text: str
    level: str = "info"
    kind: str = "sticky"
    ttl_ms: Optional[int] = None
    key: Optional[str] = None
    id: Optional[str] = None
