"""Testes do agente 42. Rode com: python3 test_agente42.py"""
from decimal import Decimal

import agente42_crescimento as a42


def test_funil_aponta_gargalo():
    r = a42.analisar_funil([("visitas", 1000), ("leads", 200), ("orcamentos", 100), ("vendas", 10)])
    taxas = [c["taxa_pct"] for c in r["conversoes"]]
    assert taxas == [Decimal("20.00"), Decimal("50.00"), Decimal("10.00")]
    assert r["gargalo"]["de"] == "orcamentos" and r["gargalo"]["para"] == "vendas"


def test_funil_exige_duas_etapas():
    try:
        a42.analisar_funil([("visitas", 100)])
    except ValueError:
        return
    raise AssertionError("deveria exigir duas etapas")


def test_pontuacao_lead_com_razoes():
    lead = {"segmento": "imobiliario", "email": "a@b.com", "pediu_orcamento": True,
            "horas_desde_ultima_resposta": 10, "ticket_estimado": 5000}
    r = a42.pontuar_lead(lead, segmentos_prioritarios={"imobiliario", "beleza_estetica"})
    assert r["pontos"] == 25 + 20 + 25 + 15 + 15  # 100
    assert r["faixa"] == "quente"
    assert len(r["razoes"]) == 5


def test_pontuacao_lead_frio():
    r = a42.pontuar_lead({"segmento": "outro"}, segmentos_prioritarios={"imobiliario"})
    assert r["pontos"] == 0 and r["faixa"] == "frio"


def test_campanha_roas_cac_lucro():
    r = a42.avaliar_campanha(investimento=1000, receita=5000, margem_bruta_pct=40, clientes_novos=10)
    assert r["roas"] == Decimal("5.00")
    assert r["cac"] == Decimal("100.00")
    # lucro bruto = 5000 * 0,40 = 2000; lucro = 2000 - 1000 = 1000
    assert r["lucro_apos_investimento"] == Decimal("1000.00")
    assert r["retorno_pct"] == Decimal("100.00")
    assert r["veredito"] == "retorno positivo"


def test_campanha_sem_retorno():
    r = a42.avaliar_campanha(investimento=1000, receita=1000, margem_bruta_pct=30, clientes_novos=0)
    assert r["lucro_apos_investimento"] == Decimal("-700.00")
    assert r["cac"] is None
    assert r["veredito"].startswith("não pagou")


def test_ponto_de_equilibrio():
    # margem unitária = 100 - 60 = 40; 4000 / 40 = 100 vendas
    assert a42.ponto_de_equilibrio(4000, 100, 60) == 100
    # arredonda para cima: 4010 / 40 = 100,25 -> 101
    assert a42.ponto_de_equilibrio(4010, 100, 60) == 101
    assert a42.ponto_de_equilibrio(4000, 50, 60) is None


def test_precificar():
    # custo 60, margem 40% -> 60 / 0,6 = 100
    assert a42.precificar(60, 40) == Decimal("100.00")
    try:
        a42.precificar(60, 100)
    except ValueError:
        return
    raise AssertionError("margem de 100% deve ser recusada")


def test_priorizacao_ice():
    acoes = [
        {"nome": "novo anúncio", "impacto": 8, "confianca": 5, "esforco": 4},   # 10
        {"nome": "ajustar oferta", "impacto": 9, "confianca": 8, "esforco": 2},  # 36
        {"nome": "trocar logo", "impacto": 2, "confianca": 9, "esforco": 9},     # 2
    ]
    ordem = [a["nome"] for a in a42.priorizar_acoes(acoes)]
    assert ordem == ["ajustar oferta", "novo anúncio", "trocar logo"]


def test_priorizacao_rejeita_valor_fora_da_faixa():
    try:
        a42.priorizar_acoes([{"nome": "x", "impacto": 11, "confianca": 5, "esforco": 5}])
    except ValueError:
        return
    raise AssertionError("valor fora de 1 a 10 deve ser recusado")


def test_plano_de_conteudo_sempre_rascunho():
    plano = a42.plano_de_conteudo(semanas=2, canais=["instagram", "tiktok"])
    assert len(plano) == 4
    assert all(p["status"] == "rascunho" and p["publicado"] is False for p in plano)
    assert plano[0]["pilar"] != plano[1]["pilar"]  # rodízio de pilares


def test_follow_up_exige_consentimento():
    assert a42.sequencia_follow_up("Ana", "imóveis", consentimento=False) == []
    assert a42.sequencia_follow_up("Ana", "imóveis", consentimento=True, optou_sair=True) == []
    mensagens = a42.sequencia_follow_up("Ana", "imóveis", consentimento=True)
    assert len(mensagens) == 3
    assert "Ana" in mensagens[0]


if __name__ == "__main__":
    testes = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    falhas = 0
    for t in testes:
        try:
            t()
            print("ok  ", t.__name__)
        except AssertionError as e:
            falhas += 1
            print("FALHA", t.__name__, e)
    print(f"\n{len(testes) - falhas}/{len(testes)} testes passaram")
    raise SystemExit(1 if falhas else 0)
