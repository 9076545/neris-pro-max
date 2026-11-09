# Provedores de IA no chat

O seletor do chat oferece três opções:

- **Neris · Cloudflare**: mantém o fluxo existente de dois modelos em sequência.
- **Gemini**: chama a Gemini API diretamente do Worker.
- **Claude · Anthropic**: chama a Messages API diretamente do Worker.

As chaves ficam exclusivamente como secrets do Worker. O endpoint público de
configuração informa somente se cada provedor está disponível; nunca retorna
valores de credenciais. O uso de Gemini e Claude pode gerar cobranças dos
respectivos provedores, além das cotas de mensagens Neris.

## Secrets e modelos

No Worker `nexus-central`, o Gemini aceita `GEMINI_API_KEY` e mantém
compatibilidade com o secret existente `Gemini_API`. O Claude requer
`ANTHROPIC_API_KEY`. Para configurar o Claude sem expor a chave no chat, use o
terminal PowerShell local:

```powershell
npx wrangler secret put ANTHROPIC_API_KEY --name nexus-central
```

O Wrangler solicita o valor localmente. Não inclua a chave em arquivos,
variáveis públicas do Wrangler ou no navegador.

Os modelos padrão são `gemini-3.5-flash-lite` e `claude-sonnet-5-5`. Podem ser
substituídos pelas variáveis não secretas `NERIS_GEMINI_MODEL` e
`NERIS_ANTHROPIC_MODEL`, respectivamente.

## Métricas do painel

Para registrar e exibir as chamadas concluídas por cérebro nos últimos sete
dias, aplique `supabase/migrations/20261110_neris_brain_usage.sql` no projeto
Supabase Neris. A migration guarda somente identificador do cérebro, data,
contagem e horário de uso; não armazena prompts nem respostas. Sem a migration,
o chat continua funcionando, mas essa métrica aparece como indisponível no
admin.
