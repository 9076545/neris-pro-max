import { DurableObject } from "cloudflare:workers";

const STARTUP_ATTEMPTS = 60;
const STARTUP_RETRY_MS = 500;
const INACTIVITY_TIMEOUT_MS = 10 * 60 * 1000;

const CONTAINER_ENV_NAMES = [
  "NERIS_ADMIN_URL",
  "NERIS_ADMIN_EMAIL",
  "NERIS_PUBLIC_URL",
  "NERIS_CHAT_URL",
  "NERIS_MOCK_MODE",
  "TURNSTILE_SECRET_KEY",
  "NEXUS_SUPABASE_URL",
  "NEXUS_SUPABASE_ANON_KEY",
  "NEXUS_OFFICE_API_URL",
  "SUPABASE_URL",
  "SUPABASE_SERVICE_ROLE_KEY",
  "CLOUDFLARE_ACCOUNT_ID",
  "CLOUDFLARE_API_TOKEN",
  "ELEVENLABS_API_KEY",
  "ELEVENLABS_VOICE_ID",
  "DEEPGRAM_API_KEY",
  "WHATSAPP_TOKEN",
  "WHATSAPP_PHONE_NUMBER_ID",
  "WHATSAPP_APP_SECRET",
  "WHATSAPP_VERIFY_TOKEN",
  "META_GRAPH_API_VERSION",
  "WHATSAPP_AGENT40_ENABLED",
  "NERIS_LEAD_NOTIFICATION_PHONE",
  "SHOPIFY_SHOP_DOMAIN",
  "SHOPIFY_ADMIN_ACCESS_TOKEN",
  "SHOPIFY_API_VERSION",
  "WEG_MQTT_HOST",
  "WEG_MQTT_PORT",
  "WEG_MQTT_USERNAME",
  "WEG_MQTT_PASSWORD",
  "WEG_MQTT_TLS",
  "WEG_OPCUA_ENDPOINT",
  "WEG_MODBUS_HOST",
  "WEG_MODBUS_PORT",
  "WEG_MODBUS_UNIT_ID",
  "ARTEMIS_BASE_URL",
  "ARTEMIS_TOKEN",
  "ARTEMIS_DEVICE_SERIAL",
  "ARTEMIS_PROFILE",
  "NERIS_ENABLE_ARTEMIS",
  "NEXUS_PLUS_WS_URL",
  "NEXUS_PLUS_SYNC_TOKEN",
];

export class AdminAPI extends DurableObject {
  starting;

  async fetch(request) {
    this.starting ??= this.startAndWaitForPort().finally(() => {
      this.starting = undefined;
    });
    await this.starting;

    const url = new URL(request.url);
    url.protocol = "http:";
    url.host = "container";
    const forwarded = new Request(url, request);
    forwarded.headers.delete("host");
    return this.ctx.container.getTcpPort(8000).fetch(forwarded);
  }

  async startAndWaitForPort() {
    const container = this.ctx.container;
    if (!container.running) {
      const env = Object.fromEntries(
        CONTAINER_ENV_NAMES.flatMap((name) =>
          typeof this.env[name] === "string" ? [[name, this.env[name]]] : [],
        ),
      );
      container.start({
        image: container.images.base,
        instance: "lite",
        enableInternet: true,
        env,
      });
    }

    await container.setInactivityTimeout(INACTIVITY_TIMEOUT_MS);
    const port = container.getTcpPort(8000);
    let lastError;
    for (let attempt = 0; attempt < STARTUP_ATTEMPTS; attempt += 1) {
      try {
        const response = await port.fetch("http://container/health", {
          signal: AbortSignal.timeout(1000),
        });
        await response.body?.cancel();
        if (!response.ok) {
          throw new Error(`FastAPI health check returned ${response.status}.`);
        }
        return;
      } catch (error) {
        lastError = error;
        await scheduler.wait(STARTUP_RETRY_MS);
      }
    }
    throw new Error("FastAPI Container did not become ready on port 8000.", {
      cause: lastError,
    });
  }
}

export default {
  fetch(request, env) {
    return env.ADMIN_API.getByName("neris-admin-api").fetch(request);
  },
};
