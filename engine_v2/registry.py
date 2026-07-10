"""
Centralny wzorzec rejestru: kazdy typ bloku (asset_filters, selector, itd.) ma wlasny slownik
nazwa -> implementacja. Implementacje rejestruja sie same (dekorator `register`), orchestrator
nigdy nie importuje konkretnych implementacji bezposrednio - tylko woła registry[name].
"""

from __future__ import annotations

from typing import Callable, Dict, TypeVar

F = TypeVar("F", bound=Callable)


def make_registry() -> Dict[str, Callable]:
    return {}


def register(registry: Dict[str, Callable], name: str):
    def decorator(fn: F) -> F:
        if name in registry:
            raise ValueError(f"Implementacja '{name}' juz zarejestrowana w tym registry.")
        registry[name] = fn
        return fn
    return decorator
