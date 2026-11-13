"""Tests for the provider module registry and profiles."""

from providers import get_provider_profile


class TestOpenRouterProfile:

    def test_sticky_session_id_normalizes_cron_timestamp(self):
        """Cron re-fires of the same job keep the same sticky routing key."""
        p = get_provider_profile("openrouter")
        first = p.build_extra_body(session_id="cron_job42_20260801_090000")
        second = p.build_extra_body(session_id="cron_job42_20260802_090000")
        assert first["session_id"] == "cron_job42"
        assert first["session_id"] == second["session_id"]

    def test_pareto_min_coding_score_emitted_for_pareto_model(self):
        """min_coding_score → plugins block when model is openrouter/pareto-code."""
        p = get_provider_profile("openrouter")
        body = p.build_extra_body(
            model="openrouter/pareto-code",
            openrouter_min_coding_score=0.65,
        )
        assert body["plugins"] == [
            {"id": "pareto-router", "min_coding_score": 0.65}
        ]

    def test_grok_session_id_sets_cache_affinity_header(self):
        """OpenRouter + Grok model + session_id => x-grok-conv-id header."""
        p = get_provider_profile("openrouter")
        _, tl = p.build_api_kwargs_extras(
            model="x-ai/grok-4",
            session_id="sess-abc123",
        )
        assert tl["extra_headers"]["x-grok-conv-id"] == "sess-abc123"

    def test_grok_conv_id_normalizes_cron_timestamp(self):
        """Cron re-fires of the same job must pin to the same xAI backend,
        same as the body.session_id sticky key (#78941)."""
        p = get_provider_profile("openrouter")
        _, first = p.build_api_kwargs_extras(
            model="x-ai/grok-4", session_id="cron_job42_20260801_090000",
        )
        _, second = p.build_api_kwargs_extras(
            model="x-ai/grok-4", session_id="cron_job42_20260802_090000",
        )
        assert first["extra_headers"]["x-grok-conv-id"] == "cron_job42"
        assert (
            first["extra_headers"]["x-grok-conv-id"]
            == second["extra_headers"]["x-grok-conv-id"]
        )

    # --- reasoning-mandatory Anthropic effort → top-level verbosity (#43432) ---
    #
    # These models (Claude 4.6+ / fable / mythos-class) ignore
    # ``reasoning.effort`` and use adaptive thinking. OpenRouter honors the
    # requested effort on the top-level ``verbosity`` field instead (maps to
    # Anthropic ``output_config.effort``). The profile must route the existing
    # ``reasoning_config["effort"]`` there while still NEVER emitting a
    # ``reasoning`` field (which would 400 — see #42991).

    def test_mandatory_anthropic_verbosity_coexists_with_grok_header(self):
        """A reasoning-mandatory Anthropic model is never a Grok model, but the
        top-level dict must remain a single merged dict — verify the verbosity
        path doesn't clobber the extra_headers slot used by Grok affinity."""
        p = get_provider_profile("openrouter")
        # mandatory anthropic + effort → verbosity, no extra_headers
        _, tl = p.build_api_kwargs_extras(
            reasoning_config={"enabled": True, "effort": "high"},
            supports_reasoning=True,
            model="anthropic/claude-fable-5",
        )
        assert tl == {"verbosity": "high"}

    def test_speed_tier_slugs_pin_endpoints_and_rewrite_wire_model(self):
        """Nous-style ``-fast``/``-flex`` slugs are OpenRouter ENDPOINTS of the base model: the wire
        model must be the base slug and ``provider.only`` must select exactly that tier, while the
        user's other routing prefs survive. The base slug itself is pinned off the flex/fast tiers."""
        import inspect
        p = get_provider_profile("openrouter")
        pins = inspect.getmodule(type(p)).OPENROUTER_ENDPOINT_PINS
        for slug, (base, tags) in pins.items():
            _, tl = p.build_api_kwargs_extras(model=slug)
            body = p.build_extra_body(model=slug, provider_preferences={"ignore": ["deepinfra"]})
            assert tl.get("model", slug) == base
            assert body["provider"] == {"ignore": ["deepinfra"], "only": list(tags)}
            tiered = [t for t in tags if t.endswith(("/fast", "/flex"))]
            assert tiered == ([] if slug == base else list(tags))
        # Unpinned model: no rewrite, prefs pass through untouched.
        _, tl = p.build_api_kwargs_extras(model="openai/gpt-5.6-sol")
        assert "model" not in tl
        assert p.build_extra_body(model="openai/gpt-5.6-sol", provider_preferences={"ignore": ["x"]})["provider"] == {"ignore": ["x"]}


class TestNousProfile:

    def test_sticky_session_id_normalizes_cron_timestamp(self):
        """Cron re-fires of the same job keep the same sticky routing key."""
        p = get_provider_profile("nous")
        first = p.build_extra_body(session_id="cron_job42_20260801_090000")
        second = p.build_extra_body(session_id="cron_job42_20260802_090000")
        assert first["session_id"] == "cron_job42"
        assert first["session_id"] == second["session_id"]

    def test_extra_body_ignores_provider_preferences(self):
        """Nous Portal rejects caller-supplied provider routing prefs (HTTP 400)."""
        p = get_provider_profile("nous")
        body = p.build_extra_body(
            provider_preferences={"allow": ["anthropic"], "sort": "price"}
        )
        assert "provider" not in body
        assert "tags" in body

