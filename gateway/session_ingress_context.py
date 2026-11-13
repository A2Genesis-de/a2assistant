"""Process-local callback provenance; private snapshots are revalidated, not grants."""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import weakref

from hermes_state_runtime import RuntimeStoreError

_callback: ContextVar[tuple | None] = ContextVar('native_ingress_callback', default=None)


def register_transport_home(runner, profile, home):
    """Called when the server creates a callback, never from event home fields."""
    homes = getattr(runner, '_native_transport_homes', None)
    if homes is None:
        homes = runner._native_transport_homes = {}
    homes[profile] = Path(home).resolve() if home is not None else None


@contextmanager
def native_callback(runner, event, transport_home, profile=None):
    if transport_home is None:
        if getattr(runner, 'session_authority', None) is not None:
            raise RuntimeStoreError('profile_mismatch')
        yield
        return
    token = _callback.set((runner, event, Path(transport_home).resolve(), profile))
    try:
        yield
    finally:
        _callback.reset(token)


def carry_callback(event, rewritten):
    """Gateway code that rebuilds a callback's event (a ``pre_gateway_dispatch`` rewrite, the
    ``/retry`` re-send) keeps the callback's provenance, but only on the source object the callback
    authenticated: a new event with a swapped source carries nothing (#139045, #139040)."""
    bound = _callback.get()
    if bound is not None and bound[1] is event and rewritten.source is event.source:
        _callback.set((bound[0], rewritten, *bound[2:]))


_PREFIX_PRODUCERS = ('webhook', 'api_server')


def _runtime_profile(runner, source, profile, owner_name):
    """The multiplexed runtime profile *source* routes to; ``_binding`` checks it is served."""
    # Same matcher as ingress stamping, ``user_id`` included: a ``user_id`` route stamps the
    # source upstream, so it must resolve here too. A route applies only to its bot_profile's
    # bot (#104933), so the receiving adapter's owner is part of the match.
    matches = [route for route in runner.config.profile_routes if route.matches(
        source.platform.value, guild_id=source.scope_id, chat_id=source.chat_id,
        thread_id=source.thread_id, parent_chat_id=source.parent_chat_id,
        adapter_profile=profile, user_id=source.user_id)]
    if source.profile and source.platform.value in _PREFIX_PRODUCERS:
        # ``/p/<profile>/`` producers address a profile explicitly on the HOST's listener; that
        # URL prefix names the profile and wins over ``profile_routes`` (webhook.py /
        # api_server.py stamp it; a bare producer source carries the routed name itself).
        return source.profile
    if matches:
        rank = max(route.specificity for route in matches)
        best = [route for route in matches if route.specificity == rank]
        if len(best) != 1:
            raise RuntimeStoreError('admission_conflict')
        return best[0].profile
    return owner_name


def _binding(runner, source, profile):
    registries = [(None, runner.adapters), *getattr(runner, '_profile_adapters', {}).items()]
    candidates = [(owner, mapping.get(source.platform)) for owner, mapping in registries]
    adapter = next((adapter for owner, adapter in candidates if owner == profile), None)
    if adapter is None or sum(item is adapter for _, item in candidates) != 1:
        raise RuntimeStoreError('not_found')
    home = getattr(runner, '_native_transport_homes', {}).get(profile)
    if home is None or not home.is_dir():
        raise RuntimeStoreError('profile_mismatch')
    runtime_home = home
    multiplex = getattr(runner.config, 'multiplex_profiles', False)
    if not multiplex and source.profile:
        raise RuntimeStoreError('profile_mismatch')
    if multiplex:
        # Only the reservation-backed server registry proves a served home. Directory
        # discovery and _resolve_profile_home_for_source's primary fallback do not.
        reserved = getattr(runner.config, '_runtime_profile_homes', None)
        if reserved is None:
            raise RuntimeStoreError('profile_mismatch')
        homes = {}
        for name, path in reserved:
            canonical = Path(path).resolve()
            if name in homes or canonical in homes.values():
                raise RuntimeStoreError('profile_mismatch')
            homes[name] = canonical
        # The primary is the reserved entry whose home IS the launch home (identity, not the
        # display name: a custom HERMES_HOME reports 'custom' while its reservation says 'default').
        from hermes_constants import get_process_hermes_home
        launch = get_process_hermes_home().resolve()
        primary = next((name for name, path in homes.items() if path == launch), None)
        if primary is None:
            raise RuntimeStoreError('profile_mismatch')
        owner_name = profile or primary
        if homes.get(owner_name) != home:
            raise RuntimeStoreError('profile_mismatch')
        runtime_profile = _runtime_profile(runner, source, profile, owner_name)
        if (source.profile or primary) != runtime_profile or runtime_profile not in homes:
            raise RuntimeStoreError('profile_mismatch')
        runtime_home = homes[runtime_profile]
        # Revoking ONE served profile (its directory removed) fails that profile only.
        if not runtime_home.is_dir():
            raise RuntimeStoreError('profile_mismatch')
    # A configured/transport home is NOT proof of a runtime DB owner: the runtime home must be
    # one this process reserved and built an authority for, never a borrowed launch DB.
    from gateway.session_authorities import authority_for_home
    authority = authority_for_home(runner, runtime_home)
    if authority is None:
        raise RuntimeStoreError('profile_mismatch')
    # The connector pins "the same credential still serves this route" across a restart. A
    # plugin platform with no discoverable credential (in-memory / socket-only adapters) is
    # still one registered adapter; it binds by platform + owning profile rather than being
    # refused as not_found.
    connector = (runner._adapter_credential_fingerprint(adapter)
                 or f'adapter:{source.platform.value}:{profile or ""}')
    if connector is None:
        raise RuntimeStoreError('not_found')
    provenance = {'transport_home': str(home), 'runtime_home': str(runtime_home),
                  'platform': source.platform.value, 'connector': connector}
    if multiplex:
        provenance['transport_profile'] = profile
    return adapter, home, runtime_home, provenance


def capture_provenance(runner, event):
    context = _callback.get()
    if context is None or context[0] is not runner or context[1] is not event:
        return None
    adapter, home, _, provenance = _binding(runner, event.source, context[3])
    owner = runner._transport_owner(event.source)
    if owner is None or owner[0] is not adapter or home != context[2]:
        raise RuntimeStoreError('not_found')
    return provenance


def restore_provenance(runner, source, provenance):
    """Resolve current owned connector/home before installing in-process auth context."""
    if not isinstance(provenance, dict):
        raise RuntimeStoreError('invalid_params')
    adapter, home, runtime_home, expected = _binding(runner, source, provenance.get('transport_profile'))
    if provenance != expected:
        raise RuntimeStoreError('profile_mismatch')
    source._transport_adapter_ref = weakref.ref(adapter)
    # Re-pin the identity ingress resolved: the drained turn's route records the receiving bot from it
    # (``SessionEntry.transport_profile``), so after a restart its session still answers through that bot.
    from gateway.session_identity import canonical_identity
    canonical_identity(source, runner=runner, adapter=adapter, transport_profile=provenance.get('transport_profile'))
    source._authorization_profile_home = home
    return runtime_home


async def reauthorize_roles(runner, source, provenance):
    """A role flag requests a connector check; it never supplies permission."""
    if not source.role_authorized:
        return False
    if provenance is None:
        raise RuntimeStoreError('invalid_params')
    restore_provenance(runner, source, provenance)
    adapter = runner._adapter_for_source(source)
    if runner._is_user_authorized_for_source(source, allow_adapter_delegation=False):
        return True  # Direct allowlist/pairing remains an independent grant.
    check = getattr(type(adapter), 'reauthorize_native_roles', None)
    if check is None:
        raise RuntimeStoreError('permission_denied')
    from gateway.run import _profile_runtime_scope
    with _profile_runtime_scope(Path(provenance['transport_home'])):
        allowed = await check(adapter, source)
    # A registry/profile/credential change during SDK I/O cannot borrow its result.
    restore_provenance(runner, source, provenance)
    if runner._adapter_for_source(source) is not adapter:
        raise RuntimeStoreError('not_found')
    if allowed is not True:
        raise RuntimeStoreError('permission_denied')
    return True


def callback_runner():
    context = _callback.get()
    return context[0] if context else None
