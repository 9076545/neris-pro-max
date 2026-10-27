"""Agente 40 · Atendimento WhatsApp (código de referência do Neris Pro Max).

Responsabilidades:
- validar o webhook da Meta (verificação GET e assinatura POST);
- identificar a empresa com no máximo uma pergunta por conversa;
- classificar o setor e manter um perfil em cache;
- rotear cada mensagem para UM único especialista;
- montar o payload de envio da WhatsApp Cloud API.

O envio real exige credenciais (token e id do número) lidos de variáveis de ambiente.
Nenhuma credencial é escrita no código.
"""
from __future__ import annotations

import hashlib
import hmac
import time
import unicodedata
from dataclasses import dataclass
from typing import Callable, Optional

MAX_TEXTO_WHATSAPP = 4096  # limite do campo de texto da Cloud API

# Setor -> sinais (palavras que aparecem no cadastro ou na descrição da empresa)
SETORES: dict[str, list[str]] = {
    "beleza_estetica": ["salao", "barbearia", "estetica", "cabelo", "manicure", "sobrancelha"],
    "saude": ["clinica", "consultorio", "dentista", "fisioterapia", "psicologia", "nutricao"],
    "alimentacao": ["restaurante", "lanchonete", "delivery", "pizzaria", "cafeteria"],
    "varejo": ["loja", "e-commerce", "ecommerce", "roupas", "calcados", "eletronicos"],
    "imobiliario": ["imobiliaria", "imoveis", "aluguel", "corretor", "locacao"],
    "educacao": ["escola", "curso", "aula", "idiomas", "reforco", "faculdade"],
    "servicos_profissionais": ["escritorio", "advocacia", "contabilidade", "consultoria", "agencia"],
    "automotivo": ["oficina", "auto center", "lava rapido", "concessionaria", "funilaria"],
    "academia_bem_estar": ["academia", "personal", "pilates", "crossfit", "yoga"],
}
SETOR_PADRAO = "servicos_gerais"

# Roteamento: ordem importa; "humano" tem prioridade absoluta.
ROTAS: list[tuple[str, list[str]]] = [
    ("humano", ["reclamacao", "reembolso", "humano", "atendente", "pessoa", "processo", "advogado"]),
    ("cancelamento", ["cancelar", "desmarcar", "remarcar"]),
    ("agendamento", ["agendar", "horario", "marcar", "disponibilidade", "amanha", "vaga"]),
    ("preco", ["preco", "quanto custa", "valor", "orcamento", "tabela"]),
]
ESPECIALISTA_PADRAO = "atendimento_geral"


def normalizar(texto: str) -> str:
    """Minúsculas, sem acentos, espaços compactados."""
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return " ".join(sem_acento.lower().split())


# ---------------------------------------------------------------- webhook Meta

def verificar_assinatura(app_secret: str, corpo_bruto: bytes, cabecalho: Optional[str]) -> bool:
    """Valida o cabeçalho X-Hub-Signature-256 (sha256=<hex> do corpo bruto)."""
    if not cabecalho or not cabecalho.startswith("sha256="):
        return False
    esperado = hmac.new(app_secret.encode(), corpo_bruto, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, cabecalho[len("sha256="):])


def responder_desafio_webhook(modo: Optional[str], token: Optional[str], desafio: Optional[str],
                              token_esperado: str) -> Optional[str]:
    """Resposta do GET de verificação. Retorna o desafio ou None (recusar)."""
    if modo == "subscribe" and token and hmac.compare_digest(token, token_esperado):
        return desafio
    return None


# ---------------------------------------------------------------- setor e perfil

def classificar_setor(texto: str) -> str:
    """Escolhe o setor com mais sinais encontrados. Empate ou nada encontrado -> servicos_gerais."""
    base = normalizar(texto)
    pontuacao = {setor: sum(1 for s in sinais if s in base) for setor, sinais in SETORES.items()}
    melhor = max(pontuacao, key=pontuacao.get)
    return melhor if pontuacao[melhor] > 0 else SETOR_PADRAO


@dataclass
class Empresa:
    id: str
    nome: str
    descricao: str
    phone_id: str


class CachePerfil:
    """Cache em memória com validade (padrão 24 h). O relógio é injetável para testes."""

    def __init__(self, ttl_segundos: int = 86400, relogio: Callable[[], float] = time.time):
        self.ttl = ttl_segundos
        self.relogio = relogio
        self._dados: dict[str, tuple[float, dict]] = {}

    def obter(self, chave: str) -> Optional[dict]:
        item = self._dados.get(chave)
        if not item:
            return None
        gravado_em, perfil = item
        if self.relogio() - gravado_em > self.ttl:
            del self._dados[chave]
            return None
        return perfil

    def guardar(self, chave: str, perfil: dict) -> None:
        self._dados[chave] = (self.relogio(), perfil)


# ---------------------------------------------------------------- identificação da empresa

@dataclass
class Resolucao:
    acao: str  # "ok" | "perguntar" | "nao_encontrada"
    empresa: Optional[Empresa] = None
    opcoes: Optional[list[str]] = None


def resolver_empresa(empresas: list[Empresa], resposta_cliente: Optional[str] = None,
                     ja_perguntou: bool = False) -> Resolucao:
    """Uma empresa -> ok, sem perguntar. Várias -> pergunta uma vez e casa a resposta com o nome."""
    if not empresas:
        return Resolucao("nao_encontrada")
    if len(empresas) == 1:
        return Resolucao("ok", empresa=empresas[0])
    if resposta_cliente is None:
        if ja_perguntou:
            return Resolucao("nao_encontrada")
        return Resolucao("perguntar", opcoes=[e.nome for e in empresas])
    alvo = normalizar(resposta_cliente)
    for e in empresas:
        if normalizar(e.nome) in alvo or alvo in normalizar(e.nome):
            return Resolucao("ok", empresa=e)
    return Resolucao("nao_encontrada")


# ---------------------------------------------------------------- roteamento

def rotear(mensagem: str) -> str:
    """Escolhe UM especialista para a mensagem. Nunca retorna mais de um."""
    base = normalizar(mensagem)
    for especialista, palavras in ROTAS:
        if any(p in base for p in palavras):
            return especialista
    return ESPECIALISTA_PADRAO


# ---------------------------------------------------------------- envio

def montar_payload_texto(destinatario: str, corpo: str) -> dict:
    """Payload da WhatsApp Cloud API para mensagem de texto (corta no limite do canal)."""
    return {
        "messaging_product": "whatsapp",
        "to": destinatario,
        "type": "text",
        "text": {"body": corpo[:MAX_TEXTO_WHATSAPP]},
    }


def extrair_mensagens(corpo_webhook: dict) -> list[dict]:
    """Lê as mensagens de texto recebidas no formato do webhook da Meta."""
    saida = []
    for entrada in corpo_webhook.get("entry", []):
        for mudanca in entrada.get("changes", []):
            valor = mudanca.get("value", {})
            phone_id = valor.get("metadata", {}).get("phone_number_id")
            for msg in valor.get("messages", []):
                if msg.get("type") == "text":
                    saida.append({
                        "phone_id": phone_id,
                        "de": msg.get("from"),
                        "texto": msg.get("text", {}).get("body", ""),
                        "timestamp": msg.get("timestamp"),
                    })
    return saida


AGENTE_40 = {
    "numero": 40,
    "id": "wa-atendimento",
    "nome": "Atendimento WhatsApp",
    "skills": ["skill-entendimento-setor"],
    "status": "pendente_integracao",  # mude para "ativo" só após os testes no seu backend
}
