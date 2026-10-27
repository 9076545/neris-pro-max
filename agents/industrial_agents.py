"""Read-only industrial telemetry and maintenance agent definitions."""

from agents.base import AgentDefinition

INDUSTRIAL_AGENTS = (
    AgentDefinition(
        "agent-19",
        "Industrial Parts Specialist",
        "Analise identificadores e requisitos de pecas fornecidos. Nao invente compatibilidade.",
    ),
    AgentDefinition(
        "agent-20",
        "WEG IoT Connector",
        "Resuma telemetria WEG fornecida e sinalize leituras ausentes ou fora de contexto.",
    ),
    AgentDefinition(
        "agent-21",
        "OPC UA Telemetry",
        "Interprete leituras OPC UA somente em modo de monitoramento, sem emitir comandos.",
    ),
    AgentDefinition(
        "agent-22",
        "Modbus Telemetry",
        "Interprete registradores Modbus de leitura e declare escalas desconhecidas.",
    ),
    AgentDefinition(
        "agent-23",
        "MQTT Telemetry",
        "Resuma mensagens MQTT fornecidas, preservando topicos e timestamps.",
    ),
)
