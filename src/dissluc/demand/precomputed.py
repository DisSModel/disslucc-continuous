"""
dissluc.demand.precomputed
--------------------------
Demanda pré-computada por passo — substrato neutro (sem GDF).
Compatível com DemandProtocol; pode ser usado com vector ou raster.
"""
from __future__ import annotations
from pathlib import Path
import csv

from dissmodel.core import Model


def load_demand_csv(
    path: str | Path,
    land_use_types: list[str],
) -> list[list[float]]:
    """
    Lê um CSV de demanda e retorna uma lista pronta para DemandPreComputedValues.

    Formato esperado do CSV — uma coluna por uso do solo, uma linha por passo:

        f,d,outros
        137878.17,19982.63,6489.20
        137622.22,20238.58,6489.20
        ...

    A ordem das colunas não precisa bater com land_use_types;
    o mapeamento é feito pelo nome do cabeçalho.

    Parâmetros
    ----------
    path : str | Path
        Caminho para o arquivo CSV.
    land_use_types : list[str]
        Nomes dos usos na ordem em que a demanda deve ser retornada.

    Retorna
    -------
    list[list[float]]
        [passo][uso] na ordem de land_use_types.
    """
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [lu for lu in land_use_types if lu not in reader.fieldnames]
        if missing:
            raise ValueError(
                f"Colunas ausentes no CSV '{path.name}': {missing}\n"
                f"Colunas disponíveis: {list(reader.fieldnames)}"
            )
        return [
            [float(row[lu]) for lu in land_use_types]
            for row in reader
        ]


class DemandPreComputedValues(Model):
    """
    Demanda pré-computada por passo de simulação.

    Parâmetros
    ----------
    annual_demand : list[list[float]]
        [passo][uso] — índice 0 = passo inicial (env.now() == 0).
        Use load_demand_csv() para carregar de um arquivo.
    land_use_types : list[str]
        Nomes dos usos do solo na mesma ordem das colunas de annual_demand.

    Exemplo
    -------
    demand = DemandPreComputedValues(
        annual_demand  = load_demand_csv("demand.csv", ["f", "d", "outros"]),
        land_use_types = ["f", "d", "outros"],
    )
    """

    INCREASING, DECREASING, STATIC = 1, -1, 0

    def setup(
        self,
        annual_demand:  list[list[float]],
        land_use_types: list[str],
    ) -> None:
        self.annual_demand    = annual_demand
        self.land_use_types   = land_use_types
        self.num_lu           = len(land_use_types)
        self.current_demand   = annual_demand[0]
        self.previous_demand  = annual_demand[0]
        self.demand_direction = [self.STATIC] * self.num_lu

    def execute(self) -> None:
        step = int(self.env.now())
        self.current_demand  = self.annual_demand[step]
        self.previous_demand = self.annual_demand[step - 1] if step > 0 else self.annual_demand[0]
        for i in range(self.num_lu):
            prev, curr = self.previous_demand[i], self.current_demand[i]
            if   step == 0 or prev == curr: self.demand_direction[i] = self.STATIC
            elif prev < curr:               self.demand_direction[i] = self.INCREASING
            else:                           self.demand_direction[i] = self.DECREASING

    # ── DemandProtocol ────────────────────────────────────────────────
    def get_current_lu_demand(self, i: int) -> float:   return self.current_demand[i]
    def get_previous_lu_demand(self, i: int) -> float:  return self.previous_demand[i]
    def get_current_lu_direction(self, i: int) -> int:  return self.demand_direction[i]
    def change_lu_direction(self, i: int) -> int:
        self.demand_direction[i] *= -1
        return self.demand_direction[i]
