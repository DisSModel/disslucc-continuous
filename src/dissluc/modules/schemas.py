"""
dissluc.schemas
---------------
Dataclasses que definem os parâmetros de cada componente.
Servem como contratos entre o usuário e os modelos — validação
acontece aqui, os modelos só consomem.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class RegressionSpec:
    """Parâmetros de uma regressão linear para um uso do solo."""
    const:  float
    betas:  dict[str, float] = field(default_factory=dict)
    is_log: bool = False


@dataclass
class AllocationSpec:
    """Restrições de alocação para um uso do solo."""
    static:     int   = -1   # -1 = respeita demanda | 0 = livre | 1 = fixo
    min_value:  float = 0.0
    max_value:  float = 1.0
    min_change: float = 0.0
    max_change: float = 1.0
