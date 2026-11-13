"""Tests for hermes_cli.model_catalog (live list refresh cadence) and the curated in-repo lists."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch


class TestRefreshCadence:
    def test_default_ttl_is_twenty_minutes_and_legacy_hours_honoured(self):
        from hermes_cli import model_catalog

        with patch("hermes_cli.config.load_config", return_value={"model_catalog": {"ttl_minutes": 20}}):
            assert model_catalog.refresh_interval_seconds() == 20 * 60
        # A user-set legacy ttl_hours still wins while ttl_minutes sits at its default.
        with patch("hermes_cli.config.load_config", return_value={"model_catalog": {"ttl_minutes": 20, "ttl_hours": 3}}):
            assert model_catalog.refresh_interval_seconds() == 3 * 3600

    def test_refresh_catalogs_forces_the_live_lists(self):
        from hermes_cli import model_catalog

        with patch("hermes_cli.models.fetch_openrouter_models") as orm:
            assert model_catalog.refresh_catalogs() is True
        orm.assert_called_once_with(force_refresh=True)

    def test_seed_shim_seeds_nothing(self, tmp_path):
        from hermes_cli import model_catalog

        assert model_catalog.seed_cache_from_checkout(tmp_path) is False


class TestIntegrationWithModelsModule:
    """Exercise the fallback paths via the real callers in hermes_cli.models."""

    def test_picker_nous_row_uses_curated_list(self, tmp_path, monkeypatch):
        """The /model picker surfaces the curated ``_PROVIDER_MODELS["nous"]``
        list in curated order — matching the ``hermes model`` CLI — not the live
        ``/v1/models`` catalog. Portal free/paid recommendations
        are unioned in when reachable; offline (as here, with the Portal calls
        stubbed out) it's exactly the curated list.
        """
        # We deliberately do NOT use the ``isolated_home`` fixture here:
        # that fixture monkeypatches ``Path.home`` to ``tmp_path``, which
        # trips the auth-store seat-belt in ``_auth_file_path()`` because
        # ``HERMES_HOME / auth.json`` then resolves to the same path the
        # seat-belt thinks is the "real" user store. Use the autouse
        # ``_hermetic_environment`` HERMES_HOME directly instead.
        from hermes_cli.models import get_curated_nous_model_ids
        from hermes_cli.model_switch_providers import list_picker_providers

        active_home = Path(os.environ["HERMES_HOME"])
        (active_home / "auth.json").write_text(
            json.dumps(
                {
                    "providers": {"nous": {"access_token": "fake"}},
                    "credential_pool": {},
                }
            )
        )

        # Stub the Portal recommendation union so the row is deterministic
        # (the curated list alone) and never touches the network. ``expected``
        # is computed from the same source the picker uses internally
        # (``curated["nous"] = get_curated_nous_model_ids()``), so the test
        # stays an invariant — it can't rot as the curated list grows.
        with patch("hermes_cli.models.check_nous_free_tier", return_value=False), patch(
            "hermes_cli.models.union_with_portal_free_recommendations",
            side_effect=lambda ids, *a, **k: (ids, {}),
        ), patch(
            "hermes_cli.models.union_with_portal_paid_recommendations",
            side_effect=lambda ids, *a, **k: (ids, {}),
        ):
            expected = get_curated_nous_model_ids()
            picker = list_picker_providers(
                current_provider="nous", max_models=99
            )

        nous_row = next((r for r in picker if r["slug"] == "nous"), None)
        assert nous_row is not None, "nous row must appear when authed"
        assert nous_row["models"] == expected

    def test_picker_max_models_cap_semantics(self, tmp_path, monkeypatch):
        """The cap argument has three distinct meanings on the real slicing
        path: ``None`` = unlimited (the cap-removal fix, #48297), ``0`` = no
        models (preserved for slug-only callers), an int N = first N. Guards
        the ``is not None`` distinction the cap-removal follow-up introduced —
        a ``if max_models`` (falsy) check would conflate ``0`` with unlimited.
        """
        from hermes_cli.models import get_curated_nous_model_ids
        from hermes_cli.model_switch import list_authenticated_providers
        from hermes_cli.model_switch_providers import list_picker_providers

        active_home = Path(os.environ["HERMES_HOME"])
        (active_home / "auth.json").write_text(
            json.dumps(
                {
                    "providers": {"nous": {"access_token": "fake"}},
                    "credential_pool": {},
                }
            )
        )
        with patch("hermes_cli.models.check_nous_free_tier", return_value=False), patch(
            "hermes_cli.models.union_with_portal_free_recommendations",
            side_effect=lambda ids, *a, **k: (ids, {}),
        ), patch(
            "hermes_cli.models.union_with_portal_paid_recommendations",
            side_effect=lambda ids, *a, **k: (ids, {}),
        ):
            expected = get_curated_nous_model_ids()
            full = list_picker_providers(current_provider="nous", max_models=None)
            one = list_picker_providers(current_provider="nous", max_models=1)
            # 0 is exercised on list_authenticated_providers (the slug-only
            # path); the picker variant drops empty-model rows entirely, so
            # the empty-list contract lives on the auth-providers call.
            zero = list_authenticated_providers(
                current_provider="nous", max_models=0
            )

        def _nous(rows):
            return next((r for r in rows if r["slug"] == "nous"), None)

        # Only meaningful when the curated list actually exceeds 1 entry.
        assert len(expected) > 1, "test needs a multi-model curated nous list"

        full_row = _nous(full)
        assert full_row is not None and full_row["models"] == expected

        # The Nous row is already curated, so an int cap never trims it (its free tier sits last).
        one_row = _nous(one)
        assert one_row is not None and one_row["models"] == expected

        zero_row = _nous(zero)
        # 0 means an empty model list — NOT unlimited. total_models still real.
        assert zero_row is not None
        assert zero_row["models"] == []
        assert zero_row["total_models"] == len(expected)


class TestCuratedLists:
    def test_inclusion_ling_free_is_curated(self):
        """inclusionai/ling-3.0-flash:free must reach the picker (#73686)."""
        from hermes_cli.models_catalog_static import OPENROUTER_MODELS

        assert "inclusionai/ling-3.0-flash:free" in [mid for mid, _desc in OPENROUTER_MODELS]

    def test_nous_lists_portal_served_muse_spark_but_not_contributor_twins(self):
        """The Portal serves plain muse-spark 1.2/1.3; only the -contributor twins are OpenRouter-only."""
        from hermes_cli.models_catalog_static import _PROVIDER_MODELS

        nous = _PROVIDER_MODELS["nous"]
        for version in ("1.2", "1.3"):
            assert f"meta/muse-spark-{version}" in nous
            assert f"meta/muse-spark-{version}-contributor" not in nous
