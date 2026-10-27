"""Agente 43 · Capital de giro, alavancagem e processamento de captação (código de referência).

Skills implementadas:
- necessidade de capital de giro (NCG) e prazos médios (PMR, PME, PMP);
- ciclo financeiro e necessidade de capital por ciclo;
- runway de caixa;
- DSCR (cobertura do serviço da dívida) e alavancagem (dívida líquida / EBITDA);
- simulação de financiamento (Tabela Price);
- processamento de captações com custo médio ponderado;
- questionário de coleta por segmento (assessorias, imobiliárias, corretores, social media e uso pessoal).

Os cálculos são determinísticos e usam Decimal para evitar erro de ponto flutuante.
Não são recomendação de investimento, crédito ou captação. Captar recursos de terceiros
pode exigir autorização de órgãos reguladores; confirme com advogado ou contador habilitado.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

D = Decimal
DOIS = D("0.01")
ZERO = D("0")
LIMITE_DSCR_ALERTA = D("1.25")   # referência comum em covenants; use o do seu contrato
LIMITE_CUSTO_ALTO_MES = D("0.10")  # 10% ao mês: sinaliza custo alto para revisão
TIPOS_CAPTACAO = {"emprestimo", "antecipacao_recebiveis", "capital_proprio", "investidor_equity", "fomento", "outro"}
TIPOS_COM_CUSTO = {"emprestimo", "antecipacao_recebiveis", "fomento"}


def _d(valor) -> Decimal:
    return D(str(valor))


def _q(valor: Decimal) -> Decimal:
    return valor.quantize(DOIS, ROUND_HALF_UP)


# ---------------------------------------------------------------- capital de giro

def necessidade_capital_giro(contas_a_receber, estoques, outros_ativos_operacionais,
                             fornecedores, outros_passivos_operacionais) -> Decimal:
    """NCG = ativos operacionais circulantes - passivos operacionais circulantes.

    Positivo: a empresa precisa financiar o giro. Negativo: os fornecedores financiam o giro.
    """
    ativos = _d(contas_a_receber) + _d(estoques) + _d(outros_ativos_operacionais)
    passivos = _d(fornecedores) + _d(outros_passivos_operacionais)
    return _q(ativos - passivos)


def prazos_medios(contas_a_receber, receita_anual, estoques, custo_anual, fornecedores,
                  dias: int = 365) -> dict:
    """PMR (dias para receber), PME (dias de estoque) e PMP (dias para pagar fornecedores)."""
    receita, custo = _d(receita_anual), _d(custo_anual)
    pmr = _q(_d(contas_a_receber) / receita * dias) if receita > ZERO else None
    pme = _q(_d(estoques) / custo * dias) if custo > ZERO else None
    pmp = _q(_d(fornecedores) / custo * dias) if custo > ZERO else None
    return {"pmr_dias": pmr, "pme_dias": pme, "pmp_dias": pmp}


def ciclo_financeiro(pmr_dias, pme_dias, pmp_dias) -> Decimal:
    """Ciclo financeiro = PMR + PME - PMP. Quanto maior, mais capital preso no giro."""
    return _q(_d(pmr_dias) + _d(pme_dias) - _d(pmp_dias))


def necessidade_por_ciclo(custo_diario, ciclo_dias) -> Decimal:
    """Capital que fica preso enquanto o ciclo financeiro não se fecha."""
    return _q(_d(custo_diario) * _d(ciclo_dias))


# ---------------------------------------------------------------- caixa, cobertura e alavancagem

def runway_meses(caixa, queima_mensal) -> Optional[Decimal]:
    """Meses de caixa com a queima atual. None se a empresa não queima caixa."""
    queima = _d(queima_mensal)
    if queima <= ZERO:
        return None
    return _q(_d(caixa) / queima)


def dscr(caixa_operacional_disponivel, servico_divida) -> dict:
    """DSCR = caixa disponível / serviço da dívida (juros + principal) no período."""
    servico = _d(servico_divida)
    if servico <= ZERO:
        return {"dscr": None, "alerta": False, "obs": "Sem serviço de dívida no período."}
    indice = _q(_d(caixa_operacional_disponivel) / servico)
    return {
        "dscr": indice,
        "alerta": indice < LIMITE_DSCR_ALERTA,
        "obs": "Abaixo da referência de 1,25; confira o covenant do seu contrato." if indice < LIMITE_DSCR_ALERTA else "Acima da referência de 1,25.",
    }


def alavancagem(divida_bruta, caixa, ebitda) -> dict:
    """Alavancagem = (dívida bruta - caixa) / EBITDA. Com EBITDA negativo, o índice não é útil."""
    if _d(ebitda) <= ZERO:
        return {"alavancagem": None, "obs": "EBITDA não positivo: o índice não é interpretável."}
    liquida = _d(divida_bruta) - _d(caixa)
    return {"alavancagem": _q(liquida / _d(ebitda)), "obs": "Dívida líquida em vezes o EBITDA anual."}


def grau_alavancagem_operacional(margem_contribuicao, ebit) -> Optional[Decimal]:
    """GAO = margem de contribuição / EBIT. Mostra a sensibilidade do lucro a variações de receita."""
    e = _d(ebit)
    if e == ZERO:
        return None
    return _q(_d(margem_contribuicao) / e)


# ---------------------------------------------------------------- financiamento

def parcela_price(valor, taxa_mensal, parcelas: int) -> Decimal:
    """Parcela na Tabela Price: P * i / (1 - (1 + i)^-n)."""
    p, i = _d(valor), _d(taxa_mensal)
    if parcelas <= 0:
        raise ValueError("parcelas deve ser positivo")
    if i == ZERO:
        return _q(p / parcelas)
    fator = (D(1) + i) ** parcelas
    return _q(p * i * fator / (fator - D(1)))


def simular_financiamento(valor, taxa_mensal, parcelas: int, receita_mensal_disponivel=None) -> dict:
    """Parcela, custo total e comprometimento da receita, se a receita for informada."""
    parcela = parcela_price(valor, taxa_mensal, parcelas)
    total = _q(parcela * parcelas)
    resultado = {
        "parcela": parcela,
        "total_pago": total,
        "custo_total": _q(total - _d(valor)),
        "comprometimento": None,
        "alerta_custo_alto": _d(taxa_mensal) > LIMITE_CUSTO_ALTO_MES,
    }
    if receita_mensal_disponivel is not None and _d(receita_mensal_disponivel) > ZERO:
        resultado["comprometimento"] = _q(parcela / _d(receita_mensal_disponivel))
    return resultado


# ---------------------------------------------------------------- processamento de captações

def processar_captacoes(entradas: list[dict]) -> dict:
    """Consolida captações. Cada entrada: {tipo, valor, taxa_mensal (opcional), prazo_meses (opcional)}.

    Retorna total por tipo, custo médio ponderado (só para tipos com custo) e alertas.
    Entradas com tipo desconhecido são rejeitadas com erro, nunca ignoradas em silêncio.
    """
    total = ZERO
    por_tipo: dict[str, Decimal] = {}
    soma_custo = ZERO
    base_custo = ZERO
    custo_total_estimado = ZERO
    alertas: list[str] = []

    for n, e in enumerate(entradas, 1):
        tipo = e.get("tipo")
        if tipo not in TIPOS_CAPTACAO:
            raise ValueError(f"entrada {n}: tipo '{tipo}' não reconhecido")
        valor = _d(e["valor"])
        if valor <= ZERO:
            raise ValueError(f"entrada {n}: valor deve ser positivo")
        total += valor
        por_tipo[tipo] = por_tipo.get(tipo, ZERO) + valor

        if tipo in TIPOS_COM_CUSTO:
            if "taxa_mensal" not in e or e["taxa_mensal"] is None:
                alertas.append(f"entrada {n} ({tipo}): sem taxa informada; não entra no custo médio.")
                continue
            taxa = _d(e["taxa_mensal"])
            prazo = int(e.get("prazo_meses", 1))
            soma_custo += taxa * valor
            base_custo += valor
            custo_total_estimado += valor * taxa * prazo
            if taxa > LIMITE_CUSTO_ALTO_MES:
                alertas.append(f"entrada {n} ({tipo}): custo acima de 10% ao mês; revisar antes de aceitar.")

    custo_medio = _q(soma_custo / base_custo) if base_custo > ZERO else None
    return {
        "total": _q(total),
        "por_tipo": {k: _q(v) for k, v in por_tipo.items()},
        "custo_medio_ponderado_mensal": custo_medio,
        "custo_total_estimado": _q(custo_total_estimado),
        "alertas": alertas,
        "obs": "Resumo contábil das entradas informadas. Não é recomendação de captação.",
    }


# ---------------------------------------------------------------- coleta por segmento

QUESTIONARIO = {
    "assessoria": [
        "Quantos clientes ativos e qual a receita mensal recorrente?",
        "Qual o prazo médio de recebimento dos clientes?",
        "Há parcelamento de honorários? Em quantas parcelas?",
        "Qual a folha e os custos fixos mensais?",
    ],
    "imobiliaria": [
        "Qual o valor mensal de aluguéis administrados e de comissões a receber?",
        "Qual o prazo entre a venda e o recebimento da comissão?",
        "Há adiantamentos a proprietários ou inquilinos pendentes?",
        "Quais as dívidas atuais e as parcelas mensais?",
    ],
    "corretor": [
        "Qual a comissão média por venda e o volume mensal?",
        "Quanto tempo leva entre a assinatura e o pagamento da comissão?",
        "Quais despesas mensais fixas e variáveis (marketing, deslocamento)?",
        "Há algum financiamento ou antecipação de recebíveis em curso?",
    ],
    "social_media": [
        "Quantos clientes pagam mensalidade e qual o ticket médio?",
        "Qual o prazo de recebimento de cada cliente (cartão, boleto, Pix)?",
        "Quais as ferramentas e os custos fixos mensais?",
        "Qual a necessidade de caixa para o próximo trimestre?",
    ],
    "uso_pessoal": [
        "Quais as suas despesas fixas e variáveis mensais?",
        "Qual é a sua renda mensal líquida?",
        "Quais dívidas você tem, com taxa e prazo de cada uma?",
        "Qual valor você quer captar e para qual finalidade?",
    ],
}


def questionario(segmento: str) -> list[str]:
    """Perguntas para coletar os dados mínimos. Uma pergunta por vez no atendimento."""
    if segmento not in QUESTIONARIO:
        raise ValueError(f"segmento '{segmento}' não cadastrado")
    return QUESTIONARIO[segmento]


AGENTE_43 = {
    "numero": 43,
    "id": "capital-de-giro",
    "nome": "Capital de Giro e Alavancagem",
    "skills": [
        "necessidade_capital_giro", "ciclo_financeiro", "runway", "dscr_alavancagem",
        "simulacao_financiamento", "processar_captacoes", "questionario_segmento",
    ],
    "status": "pendente_integracao",
}
