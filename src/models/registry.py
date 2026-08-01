# Implements: MOD-014, ARCH-010, SYS-010, REQ-013, REQ-016
"""Model registry (MOD-014 / ARCH-010).

Resolves config aliases to provider/model/auth-reference records against the
single application-layer model definition (REQ-016). ``switch_default`` is a
config-only switch that takes effect on the next resolve (REQ-016).
"""

from __future__ import annotations

from typing import Optional

from config.load import Config
from domain import ResolvedModel


class UnknownAliasError(Exception):
    """Raised for an undefined or disabled alias (REQ-013)."""

    def __init__(self, alias: str, valid_aliases: list[str]):
        self.alias = alias
        self.valid_aliases = valid_aliases
        super().__init__(f"unknown model alias '{alias}'; valid aliases: {', '.join(valid_aliases)}")


class ModelRegistry:
    def __init__(self, config: Config):
        self._config = config

    def valid_aliases(self) -> list[str]:
        return sorted(self._config.providers.keys())

    def resolve(self, alias: Optional[str] = None) -> ResolvedModel:
        """Resolve *alias* (or the configured default) to a model record."""
        a = alias or self._config.default_model
        entry = self._config.providers.get(a)
        if entry is None:
            raise UnknownAliasError(a, self.valid_aliases())
        if not entry.enabled:
            raise UnknownAliasError(a, self.valid_aliases())
        return ResolvedModel(
            alias=a,
            provider=entry.provider,
            model=entry.model,
            auth_ref=entry.auth_env or "OPENCODE_GO_TOKEN",
        )

    def switchDefault(self, alias: str) -> None:
        """Persist a new default model; takes effect on next resolve (REQ-016)."""
        if alias not in self._config.providers:
            raise UnknownAliasError(alias, self.valid_aliases())
        if not self._config.providers[alias].enabled:
            raise UnknownAliasError(alias, self.valid_aliases())
        self._config.default_model = alias

    # PEP-8 alias for switchDefault (REQ-016 config-only switch).
    def switch_default(self, alias: str) -> None:
        self.switchDefault(alias)
