# LuccME vs. disslucc-continuous: comparação arquitetural

**Fonte:** *Criando o seu componente LuccME — Um guia de desenvolvedor*, v3.1, Setembro 2017
(Equipe LuccME, CCST/INPE).

**Propósito deste documento:** registrar, com evidência, onde a arquitetura de
`disslucc-continuous` (Potential/Allocation/Demand como estratégias plugáveis,
Protocol + registry + `from_spec`) confirma, formaliza ou diverge do que o
LuccME já documentava formalmente em 2017. Serve tanto como nota técnica de
arquitetura quanto como insumo para a Etapa 1 (caracterização documental) do
projeto CNPq — o guia do LuccME é exatamente o tipo de documentação formal
que a Etapa 1 caracteriza como "o que está publicamente disponível" sobre a
linhagem de modelagem antecedente.

---

## 1. O que o guia LuccME documenta

Três componentes, chamados pelo arcabouço em ordem fixa — Demanda, depois
Potencial, depois Alocação — cada um implementando pelo menos dois métodos,
`verify` e `execute`:

> "Todo componente deve possuir pelo menos dois métodos, verify e execute...
> O Arcabouço chama primeiramente o método verify e posteriormente o execute."

`verify` é responsabilidade de cada componente, não do arcabouço: checar se
os parâmetros de entrada foram declarados e validá-los contra o banco de
dados ou faixa de valores.

O contrato entre componentes é uma **convenção de nome de coluna**, documentada
em prosa, não verificada por nenhum mecanismo do Lua:

| Componente | Entrada | Saída (convenção) |
|---|---|---|
| Demanda | demanda anual por uso do solo | `currentDemand` |
| Potencial | "não há regra específica... depende da necessidade do componente" | `cell[<lu>_pot]` |
| Alocação | tipicamente potencial + demanda, mas também "não é uma via de regra" | `cell[<lu>_out]`, `cell[<lu>_chtot]`, `cell[<lu>_chpast]` |

`_chpast` = diferença entre o valor atual e o do passo anterior.
`_chtot` = diferença entre o valor atual e o início da simulação (t0).

---

## 2. Onde a arquitetura de disslucc-continuous confirma o LuccME

### 2.1 Estrutura dos três componentes e ordem de chamada

Idêntica: `Demand → Potential → Allocation`, top-down, mesma divisão de
responsabilidade. Esperado — `disslucc-continuous` não reinventa a
arquitetura conceitual do LuccME, reimplementa em Python.

### 2.2 "Não há regra específica" de entrada → `from_spec(spec, **_ignored)`

A frase do guia sobre Potencial/Alocação — "não havendo uma regra
específica, uma vez que depende da necessidade do componente" — já
autorizava, desde 2017, o que formalizamos como convenção de chamada:
`from_spec` recebe um conjunto padrão de kwargs (`land_use_types`, `demand`,
`potential`, `gdf`/`backend`) e cada estratégia usa só o que precisa,
absorvendo o resto via `**_ignored`. Não é uma ideia nova; é a tradução
direta da filosofia já documentada.

### 2.3 `cell[<lu>_pot]` é exatamente o acoplamento que removemos

Este é o ponto mais direto de confirmação. A convenção documentada —

> "A saída de um componente de potencial deve conter... `cell[<landUseTypeName>_pot]`"

— é uma convenção *stringly-typed*: qualquer `Potential*.lua` deve escrever
nessa coluna, qualquer `Allocation*.lua` deve lê-la pelo mesmo nome, sem
camada entre os dois, e sem verificação automática — um erro de digitação no
nome da coluna falha silenciosamente ou em runtime tardio.

`AllocationClueLike` tinha exatamente essa mesma coupling (`self.gdf[lu +
"_pot"]`) antes da primeira rodada de patches deste projeto. A correção —
`self.potential.get_potential(lu)`, com `PotentialProtocol` como
`@runtime_checkable typing.Protocol` — não inventa um conceito nuevo, **torna
verificável em tempo de execução** um contrato que no LuccME existe só como
frase no PDF.

---

## 3. Onde diverge — decisões conscientes, não bugs

### 3.1 `verify()` descentralizado (LuccME) vs. centralizado no executor (disslucc-continuous)

No LuccME, cada componente valida seus próprios parâmetros via seu próprio
`verify(self, event, model)`, chamado pelo arcabouço antes do `execute()` —
uma vez por componente.

Em `disslucc-continuous`, toda validação de coluna/banda roda uma única vez
no executor (`_check_columns`/`_check_bands`), antes de `env.run()`. O
equivalente parcial ao `verify()` por componente é o hook opcional
`required_columns(spec, land_use_types)` — implementado hoje só em
`PotentialPrecomputed`, não é um contrato formal do `PotentialProtocol`.

**Não é uma lacuna corrigida neste documento** — é uma escolha arquitetural
diferente da do LuccME, registrada aqui para decisão futura: se surgir
necessidade de cada estratégia validar seus próprios parâmetros de forma
independente (ex.: `PotentialPrecomputed` verificando `bias_step >= 0` antes
de rodar), o gancho natural é promover `required_columns` a um contrato mais
amplo (`verify(spec, land_use_types) -> list[str]` retornando erros, por
exemplo), com `AllocationProtocol`/`PotentialProtocol`/`DemandProtocol`
declarando-o formalmente.

### 3.2 `_chtot` (mudança acumulada desde t0) não tem equivalente

`disslucc-continuous` mantém `_past` (valor bruto do passo anterior, via
`SyncSpatialModel`/`SyncRasterModel`), suficiente para derivar o equivalente
a `_chpast` (`atual - past`) sob demanda. **Não existe hoje nenhum mecanismo
rastreando o valor de t0** para derivar o equivalente a `_chtot`.

Isso importa especificamente para o projeto CNPq: se a decomposição Pontius
& Millones (Etapa 3) ou a comparação com os mapas publicados de Silva
Bezerra et al. (2022) precisar de "mudança acumulada desde o início" — não
só "mudança do último passo" — hoje isso exige recomputar de fora (snapshot
manual do `gdf`/`backend` em t0), não vem de graça do framework como no
LuccME.

**Status:** aberto. Duas rotas possíveis, ainda não decididas:

1. Estender `SyncSpatialModel`/`SyncRasterModel` para manter um snapshot de
   t0 automaticamente, no mesmo espírito do `_past` — mudança no `dissmodel`
   core, não em `disslucc-continuous`.
2. Tratar como responsabilidade do `dissmodel-validation` (onde a
   decomposição Pontius & Millones já está planejada para morar): o
   snapshot de t0 vira parte do protocolo de validação, não do framework de
   simulação em si.

A opção 2 parece mais alinhada à separação "DisSModel é o instrumento,
reprodutibilidade é o objeto de pesquisa" já estabelecida no projeto — mas a
decisão não foi tomada, só o gap foi documentado.

---

## 4. Resumo

| Aspecto | LuccME (Lua, 2017) | disslucc-continuous (Python) | Situação |
|---|---|---|---|
| Ordem Demand→Potential→Allocation | Sim | Sim | Confirmado |
| Contrato de entrada livre por componente | Documentado em prosa | `from_spec(spec, **_ignored)` | Formalizado |
| Ligação Potential↔Allocation | Convenção de coluna (`cell[lu_pot]`), não verificada | `PotentialProtocol.get_potential(lu)`, `@runtime_checkable` | Corrigido/endurecido |
| Validação de parâmetro (`verify`) | Por componente | Centralizada no executor | Divergência consciente, não resolvida |
| Mudança desde t0 (`_chtot`) | Convenção de saída | Não existe | Gap aberto, sem dono ainda |
| Mudança desde passo anterior (`_chpast`) | Convenção de saída | `_past`, derivável | Coberto |
