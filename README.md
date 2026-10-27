# Neris Pro Max

Aplicação com interface e API do chat em Cloudflare Workers, Workers AI para
respostas e Supabase para autenticação e persistência. A configuração gratuita
não usa Container nem servidor local. Recursos que dependem do backend Python
estão indisponíveis nessa modalidade até serem reimplementados para Workers.

## Endereços e separação de dados

- `https://neris.nexuscentralja.com.br/`: site público e apresentação dos planos.
- `https://chat.neris.nexuscentralja.com.br/`: interface do chat.
- `/leads`, `/crm` e o estúdio de projetos exibem recursos ainda dependentes do
  backend Python e não estão funcionais no deploy gratuito atual.
- `https://admin.neris.nexuscentralja.com.br/`: indisponível no deploy gratuito.

O HUD, CRM, captura e análise de leads, análise de produtos conectada ao Shopify
e geração de projetos dependem do backend FastAPI/Container e não fazem parte do
deploy gratuito atual. Essas rotas retornam erro explícito de indisponibilidade;
a interface deve apresentá-las como não disponíveis nesta edição.

O catálogo Python e o catálogo do Worker contêm 43 perfis numerados. O agente
40 permanece com status `pendente_integracao` e não pode ser selecionado no chat
nem executado como tarefa administrativa até validação; os demais perfis mantêm
seu fluxo existente. Cada conversa padrão do Worker chama o modelo especialista
e, em seguida, o modelo principal de Workers AI; isso são duas inferências/
modelos, não 43 processos autônomos. Os perfis orientam as respostas, mas só
podem usar dados enviados na conversa: não consultam automaticamente Google,
Shopify, Meta, WEG, Nexus Plus ou contas de terceiros. As 40 skills de produto
e 25 de redes sociais são instruções incluídas nos perfis correspondentes, não
ferramentas externas nem execução contínua.

O `AgentRuntime` Python, a memória pgvector e a ponte Nexus Plus Graph RAG
continuam separados do Worker Free. O segundo modelo do Worker é outro modelo
Workers AI; não é a integração Nexus Plus. Cada mensagem consome duas inferências
da cota diária de Workers AI, que pode ser esgotada mais rapidamente.

## Voz ElevenLabs

No chat web, a gravação pt-BR começa apenas após o usuário pressionar o botão e
autorizar o microfone. O áudio é enviado pelo Worker ao ElevenLabs Scribe para
transcrição; a pessoa pode revisar o texto antes de enviar à Neris. A saída
falada é gerada pelo endpoint de Text-to-Speech do ElevenLabs, com chave apenas
no servidor Cloudflare. O áudio só é criado quando a pessoa pede para ouvir.

O serviço configura `stability=0.80`, `similarity_boost=0.85`, `style=0.15` e
`use_speaker_boost=true`. A voz/gênero e o timbre dependem do `ELEVENLABS_VOICE_ID`
selecionado ou criado na conta ElevenLabs; esses parâmetros não criam uma voz
nem garantem um sotaque específico. Para obter o perfil desejado, crie ou
selecione uma voz masculina original da Neris no ElevenLabs, com uma descrição como:

> Voz masculina adulta, barítono grave e ressonante, refinada, calma e segura;
> português brasileiro natural, articulação precisa, cadência elegante e
> profissional, sem caricatura. Equilíbrio sutil entre fluidez carioca e
> clareza sulista, qualidade limpa de estúdio.

Configure `ELEVENLABS_API_KEY` e `ELEVENLABS_VOICE_ID` como secrets do Worker.
Nenhuma chave real foi fornecida nesta cópia do projeto. Sem credenciais válidas
e um voice ID existente, as rotas de voz respondem indisponibilidade; não há
fallback silencioso para voz do navegador.

ElevenLabs é um serviço externo e não está incluído na garantia de custo zero.
Deixe as chaves ausentes para manter a voz desativada no deploy gratuito.

A pipeline Pipecat disponível no módulo Python também usa ElevenLabs TTS e
Deepgram STT, mas o chat público usa as rotas Worker/ElevenLabs diretamente.
Deepgram só é necessário para iniciar essa pipeline Pipecat separadamente.

## Planos e limites

| Plano | Preço sugerido/mês | Mensagens/dia | Mensagens/mês |
|---|---:|---:|---:|
| Neris 3.5 | R$ 0,00 | 50 | 1.000 |
| Neris Pro | R$ 29,90 | 300 | 10.000 |
| Neris 5.6 | R$ 59,90 | 1.000 | 30.000 |
| Neris Ultra Max | R$ 99,90 | 3.333 | 100.000 |

Os limites são aplicados por RPC transacional no Supabase. O Ultra Max tem
limite mensal de uso justo e não é ilimitado. Voz está disponível a partir do
Pro e tem cota própria. Projetos e CRM exigem assinatura ativa Pro, 5.6 ou Ultra
Max. Os planos usam atualmente o mesmo modelo Workers AI configurado; diferem
em limites, permissões e extensão de resposta, não em uma inteligência
comprovadamente superior.

Os valores no site são sugestões informativas. Checkout, pagamentos, webhooks
da Cakto e cupons não estão implementados nem ativos. O sistema não aumenta
preços nem promete descontos automáticos. Qualquer oferta futura deve informar
valor, prazo e condições e depender da escolha do cliente.

## Cloudflare: implantação e configuração

O `wrangler.jsonc` configura Workers AI, assets e somente os dois subdomínios
públicos. Não declara Containers nem Durable Objects pagos. O deploy direto com
Wrangler não exige GitHub/Workers Builds; Containers e plano Workers Paid não
são ativados por estes passos. Workers AI e Workers Free têm limites de uso que
podem mudar; confira o painel e os limites oficiais antes de tráfego público.
Na documentação consultada em 20/10/2026, Workers Free inclui até 100.000
requisições/dia e Workers AI tem 10.000 Neurons/dia sem cobrança; cada conversa
do chat faz duas chamadas a modelos e o uso de AI acima dessa cota falha no Free
(é necessário Paid para excedente). Isso não
equivale a tráfego ou IA ilimitados. Supabase Free é separado e pode pausar
projetos inativos; serviços ElevenLabs, Deepgram, Meta, Shopify e outros também
têm termos e custos próprios.

Antes do primeiro deploy:

1. Mantenha os Workers Nexus atuais. O `wrangler.jsonc` usa apenas
   `neris.nexuscentralja.com.br` e `chat.neris.nexuscentralja.com.br`; não
   associe este Worker aos domínios raiz nem aos hostnames Nexus existentes.
   O hostname `admin.neris.nexuscentralja.com.br` não é publicado nesta versão.
2. A migration
   `supabase/migrations/20261017_neris_security_and_chat.sql` já foi aplicada
   ao projeto Supabase Neris desta implantação. Se preparar outro projeto,
   aplique-a uma vez pelo SQL Editor. Ela é aditiva: não remove políticas
   existentes. Para `logs_agentes` e `leads_prospeccao`, acrescenta políticas
   restritivas que exigem `service_role`, limitando o efeito de políticas
   permissivas anteriores.
3. No Supabase, confirme Site URL
   `https://neris.nexuscentralja.com.br` e Redirect URLs do site e chat. Para
   outro ambiente, adicione os hostnames correspondentes.
4. Na pasta do projeto, autentique o Wrangler com `npx wrangler login`. O
   navegador oficial do Cloudflare pedirá autorização da conta. Revise a conta
   e as permissões antes de aprovar; não compartilhe tokens no chat.
5. `SUPABASE_URL` já está definido como variável não secreta no
   `wrangler.jsonc`. Cadastre somente `SUPABASE_ANON_KEY` como secret: obtenha
   a chave publicável/anon em Supabase → Project Settings → API Keys e use
   `npx wrangler secret put SUPABASE_ANON_KEY`. Para a geração de vídeo,
   cadastre `MAKE_INSTAGRAM_WEBHOOK_URL` e `MAKE_INSTAGRAM_API_KEY` como secrets
   do Worker. A rota usa o cabeçalho `x-make-apikey` para a chave configurada
   na autenticação do webhook Make. Não coloque URLs/chaves reais em mensagens
   ou no repositório. Voz ElevenLabs é opcional e requer os secrets
   `ELEVENLABS_API_KEY` e `ELEVENLABS_VOICE_ID`. A service-role key, token de
   API Cloudflare e credenciais Shopify/Meta/WEG/ARTEMIS não são necessários
   para o chat e vídeo no Worker.
6. Verifique os hostnames e faça deploy com `npx wrangler deploy`. O Wrangler
   pode solicitar autorização para criar o Worker e associar os dois custom
   domains. Aprove apenas se a conta e os domínios exibidos forem os esperados.
7. Após publicar, teste `https://neris.nexuscentralja.com.br/`,
   `https://chat.neris.nexuscentralja.com.br/` e `/health`. Confirme cadastro/
   login, envio do chat, persistência e limites. Se o Wrangler indicar DNS
   ocupado ou conflito de rota, pare e resolva no painel sem alterar Workers
   Nexus existentes.

Se não houver credenciais Supabase válidas, o site estático pode publicar, mas
login, chat autenticado, cotas e persistência não estarão funcionais. O modelo
Workers AI continua vinculado pelo binding `AI`; não configure token de API
Cloudflare para essa chamada. Uso acima das cotas gratuitas ou serviços externos
podem exigir pagamento e estão fora desta garantia de gratuidade.

## WhatsApp, produtos e dados

O callback Meta existente é
`https://admin.neris.nexuscentralja.com.br/api/webhooks/meta/whatsapp`. O
arquivo `.env.example` lista os nomes sem valores. O servidor aceita
`WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_TOKEN` e
`WHATSAPP_PHONE_NUMBER_ID`; para envio também exige `META_GRAPH_API_VERSION`.
O agente 40 fica desligado por padrão (`WHATSAPP_AGENT40_ENABLED=false`) e
continua marcado `pendente_integracao`. Só depois de validar um número de teste
o operador deve habilitar o processamento no ambiente privado. A assinatura
`X-Hub-Signature-256` é verificada sobre o corpo bruto antes de processar JSON.
Respostas automáticas são limitadas a mensagens recebidas dentro de 24 horas,
uma por mensagem, sem envio em massa. Perfis identificados são mantidos somente
em cache por 24 horas; na primeira mensagem, o agente pergunta uma vez nome da
empresa e setor. `rotear()` escolhe um único especialista existente. Sem as
credenciais e a flag explícita, nenhuma resposta automática é enviada.

Notificações ao operador de respostas recebidas exigem
`NERIS_LEAD_NOTIFICATION_PHONE`, `META_WHATSAPP_NOTIFICATION_TEMPLATE` e
idioma. O template aprovado precisa aceitar dois parâmetros de texto.
Mensagens de venda para leads estão desativadas. Leads precisam consentir com o
armazenamento/uso informado; nenhuma campanha é disparada. Este projeto usa
Cloudflare Workers AI, não OpenRouter; portanto não requer
`OPENROUTER_API_KEY`.

O agente de produto consulta Shopify somente pelo endpoint administrativo
protegido. São consultados produtos e até 50 pedidos recentes com linhas de
itens, sem dados pessoais de compradores. A análise não conhece custo,
devoluções, fornecedores ou concorrentes se esses dados não forem fornecidos;
vendas passadas não garantem demanda futura. Em mock mode a amostra é
explicitamente identificada como demonstração.

## Desenvolvimento e testes locais

O `.env` existente está em mock mode e serve apenas para testes locais; os
valores `mock-*` não são credenciais. O Container de produção não copia `.env`.
Para testar o backend localmente:

```powershell
py -3.11 -m pip install -r requirements.txt
py -3.11 -m hud.server
py -3.11 -m unittest discover -s tests -t . -v
```

Para desenvolvimento local do Worker/Container, use Docker e Wrangler:

```powershell
npx wrangler dev
```

## Estrutura

- `core/`: cérebro, memória/Graph RAG, voz e estúdio de projetos.
- `agents/`: 43 definições; o runtime mantém o agente 40 pendente até validação.
- `neris_agentes/`: módulos entregues dos agentes 40-43 e skill de setor.
- `connectors/`: Shopify, Meta WhatsApp, telemetria e Artemis.
- `hud/`: API FastAPI e painel administrativo privado.
- `worker/`: Worker, site público, chat, CRM e formulários.
- `Dockerfile`: imagem do backend executada em Cloudflare Containers.
- `supabase/migrations/`: policies, histórico, quota e isolamento por proprietário.

## HUD administrativo e atividade real

O HUD FastAPI autentica o e-mail administrativo definido em
`NERIS_ADMIN_EMAIL` diretamente no Supabase Nexus e valida no servidor a
confirmação do e-mail e a autorização owner da Central JA. Configure
`NERIS_ADMIN_EMAIL`, `NEXUS_SUPABASE_URL`,
`NEXUS_SUPABASE_ANON_KEY` e `NEXUS_OFFICE_API_URL` no ambiente privado do
backend; o último deve apontar para o endpoint Nexus `/api/evento`. Nunca use a
service-role key no navegador.

O runtime cria consumidores de fila para os agentes integrados durante a vida do processo. Eles
ficam online aguardando tarefas e só chamam IA quando recebem uma tarefa; isso
não é execução autônoma contínua. A tela distingue essa atividade do feed Nexus,
que mostra apenas agentes com eventos observados. Leads mostram no máximo 500
registros recentes, pedidos Shopify no máximo 100; clientes pagantes, gastos e
visitas permanecem não conectados até existir fonte confiável para cada dado.

Código gerado é baixado como ZIP e não executado no servidor. Câmera, microfone
e integrações precisam de autorização explícita. Nenhuma implantação, DNS,
credencial real ou serviço externo foi provisionado pelo código local.

## API FastAPI e cotações de bolsa

O Worker usa `NERIS_API_BASE_URL` para encaminhar as rotas do backend; na
configuração atual, o destino é `https://admin.nexuscentralja.com.br`. Isso
apenas configura o destino do proxy e não publica o FastAPI nem configura DNS,
TLS ou o servidor de hospedagem. O backend precisa estar publicado e protegido
nesse endereço antes de habilitar as rotas dependentes.

Configure `NEXUS_SUPABASE_URL`, `NEXUS_SUPABASE_ANON_KEY` e
`TURNSTILE_SECRET_KEY` no ambiente privado do FastAPI. `SUPABASE_URL` e
`SUPABASE_SERVICE_ROLE_KEY` são configurações separadas da persistência Neris;
use apenas a chave do projeto correspondente e cadastre a service-role como
secret privado, nunca no Wrangler, no navegador ou no repositório. O arquivo
`.env.example` contém somente nomes e valores vazios.

O agente educacional 44 pode consultar até três tickers B3 explícitos na API
pública da brapi.dev. A resposta deve citar o preço, a moeda, o horário informado
pela fonte e a hora da consulta; a fonte não garante tempo real. O Worker recusa
respostas sem preço/horário válido e retorna erro explícito se a API falhar. O
recurso não acessa corretoras, não envia ordens e não recomenda comprar ou
vender ativos específicos. A disponibilidade e os limites do serviço externo
podem mudar; não há garantia de gratuidade nem de cotação em tempo real.
