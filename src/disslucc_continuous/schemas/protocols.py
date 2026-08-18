"""
disslucc_continuous.schemas.protocols
------------
Protocolos e classe base compartilhados entre substratos.

PotentialProtocol é o ponto de extensão para trocar a estratégia de
potencial (regressão linear, sample-based, precomputado por um modelo
externo, etc.) sem tocar em AllocationClueLike — equivalente ao papel
que os vários `PotentialC*.lua` cumprem no LuccME em relação a
`AllocationCClueLike.lua`. Allocation só conhece este contrato; nunca
lê `<lu>_pot` diretamente do gdf/backend nem conhece a estratégia
concreta usada para produzi-lo.
"""
from __future__ import annotations
from typing import Any, Protocol, runtime_checkable
from dissmodel.geo.vector.spatial_model import SpatialModel


@runtime_checkable
class DemandProtocol(Protocol):
    def get_current_lu_demand(self, lu_index: int) -> float: ...
    def get_previous_lu_demand(self, lu_index: int) -> float: ...
    def get_current_lu_direction(self, lu_index: int) -> int: ...
    def change_lu_direction(self, lu_index: int) -> int: ...


@runtime_checkable
class PotentialProtocol(Protocol):
    """
    Contrato mínimo que qualquer estratégia de potencial deve cumprir
    para ser usada por AllocationClueLike (vector ou raster).

    get_potential
        Retorna o potencial de mudança já calculado para o uso do solo
        `lu`, no mesmo formato usado pelo substrato (pandas Series para
        vector, np.ndarray para raster). A convenção de armazenamento
        interna (nome de coluna, layout do array etc.) é responsabilidade
        exclusiva da implementação — Allocation não deve presumir nada
        sobre ela além do retorno desta função.

    modify
        Hook de realimentação: chamado por Allocation quando a
        elasticidade satura (min/max) para empurrar o potencial de um
        uso do solo em uma direção. O que "empurrar" significa é decisão
        da estratégia (ajustar uma constante de regressão, um viés
        aditivo, ou simplesmente não fazer nada para estratégias
        totalmente precomputadas).
    """
    def get_potential(self, lu: str) -> Any: ...
    def modify(self, r_number: int, lu_idx: int, direction: int) -> None: ...

