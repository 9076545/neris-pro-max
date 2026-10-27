"""Agente 41 · Auditor de Políticas e Conformidade (código de referência).

Faz checagens automáticas no HTML ou no texto de um site e classifica cada um dos
17 itens da checklist. Quando o item depende de algo que só um humano verifica
(contraste visual, licença de imagem, veracidade de avaliações), o resultado é
NAO_VERIFICAVEL, nunca OK.

Não é aconselhamento jurídico. Toda saída traz o aviso.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

AVISO = ("Este resultado organiza uma auditoria e aponta riscos. Não é parecer jurídico. "
         "Consulte advogado ou contador habilitado para decisões.")

OK, ATENCAO, FALTA, NAO_VERIFICAVEL = "OK", "ATENÇÃO", "FALTA", "NÃO VERIFICÁVEL"

ITENS = {
    1: "Política de privacidade",
    2: "Termos de serviço",
    3: "Aviso de cookies",
    4: "Política de reembolso / arrependimento",
    5: "Formulários com consentimento (LGPD)",
    6: "Coleta somente de dados necessários",
    7: "Scripts de tracking declarados",
    8: "Acessibilidade",
    9: "Texto alternativo (alt) nas imagens",
    10: "Contraste corrigido",
    11: "Navegação por teclado",
    12: "Sem avaliações falsas",
    13: "Sem promessas falsas",
    14: "Direitos de uso das imagens",
    15: "Dados da empresa (CNPJ e contato)",
    16: "Conformidade LGPD (encarregado / contato de dados)",
    17: "Riscos jurídicos adicionais",
}

TRACKERS = ["googletagmanager", "google-analytics", "connect.facebook.net", "fbevents",
            "hotjar", "tiktok.com/i18n/pixel", "clarity.ms"]
PROMESSAS = ["garantido", "100% garantido", "cura", "melhor do mundo", "resultado certo",
             "sem risco", "ganhe dinheiro rapido"]
CNPJ = re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")


class _Coletor(HTMLParser):
    """Extrai texto visível, links, imagens, formulários, scripts e atributos de clique."""

    def __init__(self):
        super().__init__()
        self.texto: list[str] = []
        self.links: list[str] = []
        self.imagens_sem_alt = 0
        self.imagens_total = 0
        self.formularios = 0
        self.campos_pessoais = 0
        self.scripts: list[str] = []
        self.clicaveis_sem_teclado = 0
        self._ignorar = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style"):
            self._ignorar = True
            if tag == "script" and a.get("src"):
                self.scripts.append(a["src"].lower())
        if tag == "a" and a.get("href"):
            self.links.append(a["href"].lower())
        if tag == "img":
            self.imagens_total += 1
            if not (a.get("alt") or "").strip():
                self.imagens_sem_alt += 1
        if tag == "form":
            self.formularios += 1
        if tag == "input" and (a.get("type") or "text").lower() in ("email", "tel", "text"):
            self.campos_pessoais += 1
        if tag in ("div", "span") and "onclick" in a and "tabindex" not in a and "role" not in a:
            self.clicaveis_sem_teclado += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._ignorar = False

    def handle_data(self, data):
        if not self._ignorar and data.strip():
            self.texto.append(data.strip())


def _extrair(conteudo: str) -> _Coletor:
    coletor = _Coletor()
    coletor.feed(conteudo)
    coletor.texto_completo = " ".join(coletor.texto).lower()
    return coletor


def _tem(coletor: _Coletor, *termos: str) -> bool:
    alvo = coletor.texto_completo + " " + " ".join(coletor.links)
    return any(t in alvo for t in termos)


def auditar(conteudo: str, eh_loja: bool | None = None) -> dict:
    """Audita o HTML (ou texto) de uma página e devolve os 17 itens com status e evidência.

    eh_loja: se None, é detectado pela presença de 'carrinho' ou 'comprar'.
    """
    c = _extrair(conteudo)
    if eh_loja is None:
        eh_loja = _tem(c, "carrinho", "comprar", "finalizar pedido")

    r: dict[int, tuple[str, str]] = {}

    r[1] = (OK, "Link ou texto de política de privacidade encontrado.") if _tem(c, "política de privacidade", "politica de privacidade", "privacidade") else (FALTA, "Não encontrei política de privacidade.")
    r[2] = (OK, "Termos de uso/serviço encontrados.") if _tem(c, "termos de uso", "termos de serviço", "termos de servico") else (FALTA, "Não encontrei termos de uso ou de serviço.")

    if _tem(c, "cookie"):
        r[3] = (OK, "Aviso de cookies citado.") if _tem(c, "aceitar", "consentimento") else (ATENCAO, "Cookies citados, mas sem botão ou texto de aceite.")
    else:
        r[3] = (FALTA, "Não encontrei aviso de cookies.")

    if _tem(c, "reembolso", "arrependimento", "política de troca", "politica de troca", "troca"):
        r[4] = (OK, "Política de reembolso, troca ou arrependimento citada.")
    elif eh_loja:
        r[4] = (FALTA, "Loja sem política de reembolso/arrependimento visível.")
    else:
        r[4] = (ATENCAO, "Não encontrei política de reembolso; confirme se ela se aplica ao seu negócio.")

    if c.formularios and c.campos_pessoais:
        r[5] = (OK, "Formulário com consentimento citado.") if _tem(c, "consentimento", "lgpd", "concordo") else (ATENCAO, "Formulário coleta dados sem texto de consentimento visível.")
    else:
        r[5] = (NAO_VERIFICAVEL, "Nenhum formulário encontrado para avaliar.")

    r[6] = (NAO_VERIFICAVEL, "Só uma análise humana do que é realmente necessário pode confirmar.")

    trackers = [s for s in c.scripts if any(t in s for t in TRACKERS)]
    if trackers:
        r[7] = (OK, "Tracking declarado.") if _tem(c, "cookie", "privacidade") else (ATENCAO, f"{len(trackers)} script(s) de tracking sem declaração na política.")
    else:
        r[7] = (OK, "Nenhum script de tracking conhecido encontrado.")

    if c.imagens_sem_alt:
        r[8] = (ATENCAO, f"{c.imagens_sem_alt} de {c.imagens_total} imagem(ns) sem texto alternativo.")
        r[9] = (ATENCAO, f"{c.imagens_sem_alt} imagem(ns) sem alt.")
    else:
        r[8] = (OK if c.imagens_total else NAO_VERIFICAVEL, "Imagens com alt." if c.imagens_total else "Sem imagens para avaliar.")
        r[9] = (OK if c.imagens_total else NAO_VERIFICAVEL, "Todas as imagens têm alt." if c.imagens_total else "Sem imagens para avaliar.")

    r[10] = (NAO_VERIFICAVEL, "Contraste depende da renderização; use uma ferramenta de contraste.")
    r[11] = (ATENCAO, f"{c.clicaveis_sem_teclado} elemento(s) clicáveis sem tabindex/role.") if c.clicaveis_sem_teclado else (OK, "Nenhum elemento clicável sem suporte a teclado encontrado.")
    r[12] = (NAO_VERIFICAVEL, "Só a origem real das avaliações confirma se são verdadeiras.")

    achados = [p for p in PROMESSAS if p in c.texto_completo]
    r[13] = (ATENCAO, "Termos de promessa absoluta: " + ", ".join(achados)) if achados else (OK, "Nenhuma promessa absoluta encontrada pelas palavras-chave.")

    r[14] = (NAO_VERIFICAVEL, "Só a licença de cada imagem confirma o direito de uso.")

    if CNPJ.search(conteudo):
        r[15] = (OK, "CNPJ encontrado.")
    else:
        r[15] = (FALTA, "Nenhum CNPJ visível na página.")

    if _tem(c, "encarregado", "dpo", "dados@", "privacidade@"):
        r[16] = (OK, "Contato de dados ou encarregado encontrado.")
    else:
        r[16] = (FALTA, "Não encontrei encarregado ou contato de dados.")

    graves = [n for n in (1, 2, 15, 16) if r[n][0] == FALTA]
    r[17] = (ATENCAO if graves else OK, "Itens críticos em falta: " + ", ".join(map(str, graves)) if graves else "Nenhum risco crítico adicional identificado pelas checagens.")

    itens = [{"numero": n, "item": ITENS[n], "status": r[n][0], "evidencia": r[n][1]} for n in range(1, 18)]
    return {"itens": itens, "risco": _risco(itens), "aviso": AVISO}


def _risco(itens: list[dict]) -> str:
    criticos = {1, 2, 15, 16}
    if any(i["status"] == FALTA and i["numero"] in criticos for i in itens):
        return "alto"
    if any(i["status"] in (FALTA, ATENCAO) for i in itens):
        return "médio"
    return "baixo"


def plano_de_correcao(resultado: dict, limite: int = 5) -> list[str]:
    """Lista de correções priorizadas, críticas primeiro (máximo `limite`)."""
    ordem = sorted((i for i in resultado["itens"] if i["status"] in (FALTA, ATENCAO)),
                   key=lambda i: (i["status"] != FALTA, i["numero"]))
    return [f"{i['numero']}. {i['item']}: {i['evidencia']}" for i in ordem[:limite]]


AGENTE_41 = {
    "numero": 41,
    "id": "auditor-politicas",
    "nome": "Auditor de Políticas e Conformidade",
    "status": "pendente_integracao",
}
