"""``auth_type`` dispatch table for the auxiliary registry branch.

``_resolve_registry_branch`` in ``agent/auxiliary_client`` routes every
``PROVIDER_REGISTRY`` provider here on its registered ``auth_type``; this table is the
registry twin of the facade's ``_EXPLICIT_PROVIDER_BRANCHES``. Arms late-import the
facade (siblings never form a module-level cycle) so the seam every test patches —
``agent.auxiliary_client.*`` — is the module production reads.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Dict

if TYPE_CHECKING:
    from agent.auxiliary_client import _ResolveRequest, _ResolveResult

logger = logging.getLogger("agent.auxiliary_client")


def _resolve_plugin_oauth_arm(req: _ResolveRequest) -> _ResolveResult:
    from agent.auxiliary_plugin_oauth import resolve_plugin_oauth_client
    return resolve_plugin_oauth_client(req)


# ``api_key`` / ``external_process`` arms stay on the facade (they share its credential
# resolvers); the table maps the auth types whose arms are build-and-route one-liners
# or live here as topical arms.
REGISTRY_AUTHTYPE_ARMS: dict[str, Callable[[_ResolveRequest], _ResolveResult]] = {
    # Plugin OAuth: nous / openai-codex / xai-oauth returned from their explicit branches.
    "oauth_device_code": _resolve_plugin_oauth_arm,
    "oauth_external": _resolve_plugin_oauth_arm,
}
