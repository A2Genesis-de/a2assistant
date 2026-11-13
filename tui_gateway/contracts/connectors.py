"""Contracts for connector catalog, authorization, and tool-list reads."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .base import Result, WireEnum
from .common import ConnectorOwner, ProfileParams
from .connectors_operation import ConnectionOperationStatus
from .registry import method

ConnectorSlug = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")]
# The name of one hosted account of a connector (the gateway's account alias format).
ConnectorAlias = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{0,31}$")]


class ConnectorErrorReason(WireEnum):
    invalid_params = "INVALID_PARAMS"
    not_owner = "NOT_OWNER"
    unsupported_runtime = "UNSUPPORTED_RUNTIME"
    connector_request_failed = "CONNECTOR_REQUEST_FAILED"
    invalid_connector_response = "INVALID_CONNECTOR_RESPONSE"
    unknown_target = "UNKNOWN_TARGET"
    link_still_valid = "LINK_STILL_VALID"
    reissue_refused = "REISSUE_REFUSED"
    unknown_operation = "UNKNOWN_OPERATION"
    invalid_answer = "INVALID_ANSWER"
    needs_nous_auth = "NEEDS_NOUS_AUTH"
    connector_not_found = "CONNECTOR_NOT_FOUND"
    tools_unavailable = "TOOLS_UNAVAILABLE"
    connectors_unavailable = "CONNECTORS_UNAVAILABLE"
    catalog_unavailable = "CATALOG_UNAVAILABLE"
    accounts_unavailable = "ACCOUNTS_UNAVAILABLE"
    connection_not_found = "CONNECTION_NOT_FOUND"
    policy_unavailable = "POLICY_UNAVAILABLE"
    policy_conflict = "POLICY_CONFLICT"
    forbidden_scope = "FORBIDDEN_SCOPE"
    org_required = "ORG_REQUIRED"
    org_access_denied = "ORG_ACCESS_DENIED"
    invalid_policy = "INVALID_POLICY"
    alias_taken = "ALIAS_TAKEN"


class ConnectorsListParams(ProfileParams):
    owner: ConnectorOwner


class ConnectorRow(Result):
    connector: str
    enabled: bool
    connected: bool
    connection_status: Literal["pending", "active", "failed", "expired", "revoked", "inactive"] | None
    status_reason: str | None
    gateway_disabled_tools: list[str]


class ConnectorsListResult(Result):
    available: bool
    connectors: list[ConnectorRow]


method(
    "connectors.list",
    params=ConnectorsListParams,
    result=ConnectorsListResult,
    doc="Connector catalog + connection state for one session or profile account owner.",
)


class ConnectorsConnectParams(ProfileParams):
    owner: ConnectorOwner
    connectors: list[ConnectorSlug] = Field(min_length=1)
    reconnect: bool = False
    # Connects (or, with ``reconnect``, repairs) the account of that name; one connector per call.
    alias: ConnectorAlias | None = None
    # With ``reconnect``: repairs this existing account, the only way to address an unnamed one.
    connection_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _one_connector_per_alias(self):
        if self.alias is not None and len(self.connectors) != 1:
            raise ValueError("alias names one account, so it takes exactly one connector")
        if self.connection_id is not None and (not self.reconnect or len(self.connectors) != 1 or self.alias):
            raise ValueError("connection_id repairs one account: it needs reconnect, one connector and no alias")
        return self


class ConnectorsConnectResult(ConnectionOperationStatus):
    """``methods_connectors._reissue`` / ``managed._off_desktop_result``: the operation the connect opened; ``status``/``note`` ride along from the tool result."""

    status: Literal["initiated", "settled"] | None = None
    note: str | None = None


method(
    "connectors.connect",
    params=ConnectorsConnectParams,
    result=ConnectorsConnectResult,
    doc="Start or re-initiate authorization for named connectors on a session or account operation.",
)
