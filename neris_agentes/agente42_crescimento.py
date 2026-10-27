"""Agente 42 · Crescimento: vendas e marketing (código de referência do Neris Pro Max).

Skills viáveis agora, sem integrações externas:
- analisar_funil: taxa de conversão entre etapas e o maior gargalo;
- pontuar_lead: pontuação por regras explícitas, com a razão de cada ponto;
- avaliar_campanha: ROAS, CAC, lucro e retorno sobre o investimento;
- ponto_de_equilibrio e precificar: quantas vendas pagam os custos, e o preço que atinge a margem;
- priorizar_acoes: ranking por impacto, confiança e esforço (nota ICE);
- plano_de_conteudo: calendário em RASCUNHO, sem publicar nada;
- sequencia_follow_up: mensagens em RASCUNHO, só para contatos com consentimento.

Não faz, por decisão de desenho:
- publicar em redes sociais de forma automática;
- disparar mensagens em massa no WhatsApp;
- alterar verba de anúncios;
- coletar dados de concorrentes.

Os cálculos usam Decimal. Não são garantia de resultado nem recomendação de investimento.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

D = Decimal
DOIS = D("0.01")
ZERO = D("0")


def _d(v) -> Decimal:
    return D(str(v))


def _q(v: Decimal) -> Decimal:
    return v.quantize(DOIS, ROUND_HALF_UP)


# ---------------------------------------------------------------- funil

def analisar_funil(etapas: list[tuple[str, int]]) -> dict:
    """etapas: lista ordenada [(nome, quantidade)], do topo ao fundo.

    Retorna a conversão entre etapas e a etapa com a pior conversão (o gargalo).
    """
    if len(etapas) < 2:
        raise ValueError("o funil precisa de pelo menos duas etapas")
    conversoes = []
    for (nome_a, qa), (nome_b, qb) in zip(etapas, etapas[1:]):
        taxa = _q(_d(qb) / _d(qa) * 100) if qa > 0 else None
        conversoes.append({"de": nome_a, "para": nome_b, "taxa_pct": taxa})
    validas = [c for c in conversoes if c["taxa_pct"] is not None]
    gargalo = min(validas, key=lambda c: c["taxa_pct"]) if validas else None
    return {
        "conversoes": conversoes,
        "gargalo": gargalo,
        "obs": "O gargalo é a etapa com menor taxa. Comece a melhorar por ela.",
    }


# ---------------------------------------------------------------- leads

PESOS_LEAD = {
    "segmento_prioritario": 25,
    "contato_valido": 20,
    "pediu_orcamento": 25,
    "respondeu_nas_ultimas_48h": 15,
    "ticket_estimado_alto": 15,
}


def pontuar_lead(lead: dict, segmentos_prioritarios: set[str], ticket_alto: float = 2000) -> dict:
    """Pontuação de 0 a 100 com a razão de cada ponto. Regras visíveis, sem caixa-preta."""
    pontos = 0
    razoes: list[str] = []

    if lead.get("segmento") in segmentos_prioritarios:
        pontos += PESOS_LEAD["segmento_prioritario"]
        razoes.append(f"segmento prioritário ({lead['segmento']}) +{PESOS_LEAD['segmento_prioritario']}")
    if lead.get("email") or lead.get("whatsapp"):
        pontos += PESOS_LEAD["contato_valido"]
        razoes.append(f"contato válido +{PESOS_LEAD['contato_valido']}")
    if lead.get("pediu_orcamento"):
        pontos += PESOS_LEAD["pediu_orcamento"]
        razoes.append(f"pediu orçamento +{PESOS_LEAD['pediu_orcamento']}")
    if lead.get("horas_desde_ultima_resposta") is not None and lead["horas_desde_ultima_resposta"] <= 48:
        pontos += PESOS_LEAD["respondeu_nas_ultimas_48h"]
        razoes.append(f"respondeu nas últimas 48 h +{PESOS_LEAD['respondeu_nas_ultimas_48h']}")
    if lead.get("ticket_estimado") is not None and _d(lead["ticket_estimado"]) >= _d(ticket_alto):
        pontos += PESOS_LEAD["ticket_estimado_alto"]
        razoes.append(f"ticket estimado acima de {ticket_alto} +{PESOS_LEAD['ticket_estimado_alto']}")

    faixa = "quente" if pontos >= 60 else "morno" if pontos >= 30 else "frio"
    return {"pontos": pontos, "faixa": faixa, "razoes": razoes}


# ---------------------------------------------------------------- campanhas e dinheiro

def avaliar_campanha(investimento, receita, margem_bruta_pct, clientes_novos: int) -> dict:
    """ROAS, CAC, lucro e retorno. margem_bruta_pct em percentual (ex.: 40 para 40%)."""
    inv, rec = _d(investimento), _d(receita)
    if inv <= ZERO:
        raise ValueError("investimento deve ser positivo")
    margem = _d(margem_bruta_pct) / D(100)
    lucro_bruto = rec * margem
    lucro = lucro_bruto - inv
    return {
        "roas": _q(rec / inv),
        "cac": _q(inv / clientes_novos) if clientes_novos > 0 else None,
        "lucro_apos_investimento": _q(lucro),
        "retorno_pct": _q(lucro / inv * 100),
        "veredito": "retorno positivo" if lucro > ZERO else "não pagou o investimento neste período",
    }


def ponto_de_equilibrio(custos_fixos_mensais, preco_medio, custo_variavel_unitario) -> Optional[int]:
    """Quantas vendas por mês cobrem os custos fixos. None se a margem de contribuição não for positiva."""
    margem_unit = _d(preco_medio) - _d(custo_variavel_unitario)
    if margem_unit <= ZERO:
        return None
    vendas = _d(custos_fixos_mensais) / margem_unit
    return int(vendas.to_integral_value(rounding="ROUND_CEILING"))


def precificar(custo_unitario, margem_desejada_pct) -> Decimal:
    """Preço que entrega a margem desejada: custo / (1 - margem)."""
    m = _d(margem_desejada_pct) / D(100)
    if m >= 1:
        raise ValueError("margem deve ser menor que 100%")
    return _q(_d(custo_unitario) / (D(1) - m))


# ---------------------------------------------------------------- priorização

def priorizar_acoes(acoes: list[dict]) -> list[dict]:
    """Nota ICE = impacto * confiança / esforço. Cada valor de 1 a 10. Maior nota primeiro."""
    for a in acoes:
        for campo in ("impacto", "confianca", "esforco"):
            if not 1 <= a[campo] <= 10:
                raise ValueError(f"{a['nome']}: {campo} deve estar entre 1 e 10")
    ranqueadas = [dict(a, nota_ice=_q(_d(a["impacto"]) * _d(a["confianca"]) / _d(a["esforco"])))
                  for a in acoes]
    return sorted(ranqueadas, key=lambda a: a["nota_ice"], reverse=True)


# ---------------------------------------------------------------- conteúdo e follow-up (sempre rascunho)

PILARES_PADRAO = ["problema do cliente", "prova social", "bastidores", "oferta", "educação"]


def plano_de_conteudo(semanas: int, canais: list[str], pilares: list[str] | None = None) -> list[dict]:
    """Calendário em rascunho: um pilar por post, em rodízio. Nada é publicado."""
    pilares = pilares or PILARES_PADRAO
    if semanas < 1 or not canais:
        raise ValueError("informe ao menos 1 semana e 1 canal")
    plano, i = [], 0
    for semana in range(1, semanas + 1):
        for canal in canais:
            plano.append({"semana": semana, "canal": canal, "pilar": pilares[i % len(pilares)],
                          "status": "rascunho", "publicado": False})
            i += 1
    return plano


def sequencia_follow_up(nome: str, segmento: str, consentimento: bool, optou_sair: bool = False) -> list[str]:
    """Rascunhos de follow-up. Vazio se não houver consentimento ou se a pessoa pediu para sair."""
    if not consentimento or optou_sair:
        return []
    return [
        f"Oi, {nome}! Você pediu informações sobre {segmento}. Posso te mostrar como funciona?",
        f"{nome}, passando para saber se ficou alguma dúvida sobre {segmento}. Quer conversar?",
        f"Última mensagem por aqui, {nome}. Se mudar de ideia, é só responder esta conversa.",
    ]


AGENTE_42 = {
    "numero": 42,
    "id": "crescimento",
    "nome": "Crescimento: vendas e marketing",
    "skills": [
        "analisar_funil", "pontuar_lead", "avaliar_campanha", "ponto_de_equilibrio",
        "precificar", "priorizar_acoes", "plano_de_conteudo", "sequencia_follow_up",
    ],
    "fora_do_escopo": [
        "publicar automaticamente em redes sociais",
        "disparo em massa de WhatsApp",
        "alterar verba de anúncios",
        "coleta de dados de concorrentes",
    ],
    "status": "pendente_integracao",
}
