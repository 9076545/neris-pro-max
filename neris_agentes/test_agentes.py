"""Testes dos agentes 40, 41 e 43. Rode com: python3 test_agentes.py  (ou pytest)."""
import hashlib
import hmac
from decimal import Decimal

import agente40_whatsapp as a40
import agente41_auditor as a41
import agente43_capital_giro as a43


# ---------------------------------------------------------------- agente 40

def test_assinatura_meta():
    segredo, corpo = "segredo-de-teste", b'{"entry": []}'
    assinatura = "sha256=" + hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()
    assert a40.verificar_assinatura(segredo, corpo, assinatura)
    assert not a40.verificar_assinatura(segredo, corpo + b" ", assinatura)  # corpo alterado
    assert not a40.verificar_assinatura(segredo, corpo, None)
    assert not a40.verificar_assinatura(segredo, corpo, "md5=abc")


def test_desafio_webhook():
    assert a40.responder_desafio_webhook("subscribe", "tok", "123", "tok") == "123"
    assert a40.responder_desafio_webhook("subscribe", "errado", "123", "tok") is None
    assert a40.responder_desafio_webhook("unsubscribe", "tok", "123", "tok") is None


def test_classificar_setor():
    assert a40.classificar_setor("Salão de beleza Studio Ju") == "beleza_estetica"
    assert a40.classificar_setor("Clínica odontológica Sorriso") == "saude"
    assert a40.classificar_setor("Escritório de advocacia") == "servicos_profissionais"
    assert a40.classificar_setor("Empresa sem descrição útil") == "servicos_gerais"


def test_resolver_empresa():
    unica = [a40.Empresa("1", "Studio Ju", "salão", "p1")]
    assert a40.resolver_empresa(unica).acao == "ok"  # não pergunta
    varias = [a40.Empresa("1", "Studio Ju", "", "p1"), a40.Empresa("2", "Clínica Sorriso", "", "p1")]
    assert a40.resolver_empresa(varias).acao == "perguntar"
    assert a40.resolver_empresa(varias, resposta_cliente="Sou da Studio Ju").empresa.id == "1"
    assert a40.resolver_empresa(varias, resposta_cliente="Padaria X").acao == "nao_encontrada"
    # já perguntou e a resposta não veio: não pergunta de novo
    assert a40.resolver_empresa(varias, resposta_cliente=None, ja_perguntou=True).acao == "nao_encontrada"


def test_rotear_um_especialista():
    assert a40.rotear("Quanto custa o corte?") == "preco"
    assert a40.rotear("Tem horário amanhã?") == "agendamento"
    assert a40.rotear("Quero cancelar meu horário") == "cancelamento"
    assert a40.rotear("Quero falar com uma pessoa") == "humano"
    assert a40.rotear("Quero cancelar e pedir reembolso") == "humano"  # humano tem prioridade
    assert a40.rotear("Bom dia") == "atendimento_geral"


def test_cache_expira():
    relogio = [1000.0]
    cache = a40.CachePerfil(ttl_segundos=60, relogio=lambda: relogio[0])
    cache.guardar("num", {"setor": "saude"})
    assert cache.obter("num") == {"setor": "saude"}
    relogio[0] += 61
    assert cache.obter("num") is None


def test_payload_respeita_limite():
    p = a40.montar_payload_texto("5579", "x" * 5000)
    assert len(p["text"]["body"]) == a40.MAX_TEXTO_WHATSAPP
    assert p["messaging_product"] == "whatsapp"


# ---------------------------------------------------------------- agente 41

HTML_OK = """<html><body>
<a href="/privacidade">Política de privacidade</a> <a href="/termos">Termos de uso</a>
<div>Usamos cookies. <button>Aceitar</button></div>
<a href="/troca">Política de troca e arrependimento</a>
<form><input type="email"><div>Concordo com o tratamento de dados (LGPD)</div></form>
<img src="a.jpg" alt="Foto do salão">
<footer>Empresa Ltda, CNPJ 12.345.678/0001-90. Encarregado: dados@exemplo.com.br</footer>
</body></html>"""

HTML_RUIM = """<html><body>
<p>Garantido! 100% garantido, a cura é certa.</p>
<img src="a.jpg">
<div onclick="comprar()">Comprar</div>
</body></html>"""


def test_auditor_site_completo():
    r = a41.auditar(HTML_OK, eh_loja=False)
    status = {i["numero"]: i["status"] for i in r["itens"]}
    assert status[1] == a41.OK and status[2] == a41.OK and status[15] == a41.OK and status[16] == a41.OK
    assert status[9] == a41.OK
    assert r["risco"] == "baixo" or r["risco"] == "médio"
    assert r["aviso"] == a41.AVISO


def test_auditor_site_ruim_marca_falta_e_nao_inventa_ok():
    r = a41.auditar(HTML_RUIM, eh_loja=True)
    status = {i["numero"]: i["status"] for i in r["itens"]}
    assert status[1] == a41.FALTA            # sem privacidade
    assert status[15] == a41.FALTA           # sem CNPJ
    assert status[4] == a41.FALTA            # loja sem reembolso
    assert status[13] == a41.ATENCAO         # promessa absoluta
    assert status[11] == a41.ATENCAO         # clicável sem teclado
    assert status[14] == a41.NAO_VERIFICAVEL  # nunca OK sem prova humana
    assert status[12] == a41.NAO_VERIFICAVEL
    assert r["risco"] == "alto"


def test_auditor_plano_prioriza_faltas():
    r = a41.auditar(HTML_RUIM, eh_loja=True)
    plano = a41.plano_de_correcao(r)
    assert plano[0].startswith("1.") or plano[0].startswith("2.") or plano[0].startswith("4.")
    assert len(plano) <= 5


# ---------------------------------------------------------------- agente 43

def test_ncg():
    assert a43.necessidade_capital_giro(100000, 50000, 0, 30000, 0) == Decimal("120000.00")
    # fornecedores maiores que o ativo: a empresa é financiada pelos fornecedores
    assert a43.necessidade_capital_giro(10000, 0, 0, 30000, 0) == Decimal("-20000.00")


def test_prazos_e_ciclo():
    p = a43.prazos_medios(36500, 365000, 20000, 200000, 10000)
    assert p["pmr_dias"] == Decimal("36.50")
    assert p["pme_dias"] == Decimal("36.50")
    assert p["pmp_dias"] == Decimal("18.25")
    assert a43.ciclo_financeiro(p["pmr_dias"], p["pme_dias"], p["pmp_dias"]) == Decimal("54.75")


def test_runway_sem_queima():
    assert a43.runway_meses(10000, 2500) == Decimal("4.00")
    assert a43.runway_meses(10000, 0) is None


def test_dscr_limite():
    assert a43.dscr(5000, 4000)["dscr"] == Decimal("1.25")
    assert a43.dscr(5000, 4000)["alerta"] is False  # 1,25 não está abaixo da referência
    assert a43.dscr(4000, 4000)["dscr"] == Decimal("1.00")
    assert a43.dscr(4000, 4000)["alerta"] is True
    assert a43.dscr(4000, 0)["dscr"] is None


def test_alavancagem():
    assert a43.alavancagem(500000, 100000, 200000)["alavancagem"] == Decimal("2.00")
    assert a43.alavancagem(500000, 100000, -1)["alavancagem"] is None


def test_price():
    parcela = a43.parcela_price(1000, Decimal("0.02"), 12)
    assert abs(parcela - Decimal("94.56")) < Decimal("0.02")
    assert a43.parcela_price(1200, 0, 12) == Decimal("100.00")


def test_simulacao_alerta_custo():
    s = a43.simular_financiamento(1000, Decimal("0.12"), 12, receita_mensal_disponivel=500)
    assert s["alerta_custo_alto"] is True
    assert s["comprometimento"] is not None


def test_captacoes_custo_medio_e_alertas():
    r = a43.processar_captacoes([
        {"tipo": "emprestimo", "valor": 10000, "taxa_mensal": Decimal("0.05"), "prazo_meses": 10},
        {"tipo": "capital_proprio", "valor": 5000},
        {"tipo": "antecipacao_recebiveis", "valor": 2000, "taxa_mensal": Decimal("0.12"), "prazo_meses": 1},
    ])
    assert r["total"] == Decimal("17000.00")
    assert r["por_tipo"]["capital_proprio"] == Decimal("5000.00")
    assert r["custo_medio_ponderado_mensal"] == Decimal("0.06")
    assert r["custo_total_estimado"] == Decimal("5240.00")
    assert any("10% ao mês" in a for a in r["alertas"])


def test_captacao_sem_taxa_avisa():
    r = a43.processar_captacoes([{"tipo": "emprestimo", "valor": 1000}])
    assert r["custo_medio_ponderado_mensal"] is None
    assert r["alertas"]


def test_captacao_rejeita_tipo_desconhecido():
    try:
        a43.processar_captacoes([{"tipo": "cripto-bonus", "valor": 100}])
    except ValueError:
        return
    raise AssertionError("deveria rejeitar tipo desconhecido")


def test_questionario_segmentos():
    for seg in ["assessoria", "imobiliaria", "corretor", "social_media", "uso_pessoal"]:
        assert len(a43.questionario(seg)) == 4
    try:
        a43.questionario("inexistente")
    except ValueError:
        return
    raise AssertionError("deveria rejeitar segmento inexistente")


if __name__ == "__main__":
    tests = [value for name, value in globals().items() if name.startswith("test_")]
    failures = []
    for test in tests:
        try:
            test()
            print("ok  ", test.__name__)
        except AssertionError as error:
            failures.append((test.__name__, error))
            print("FALHA", test.__name__, error)
    print(f"\n{len(tests) - len(failures)}/{len(tests)} testes passaram")
    raise SystemExit(bool(failures))


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
