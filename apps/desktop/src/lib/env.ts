import { FRONTEND_API_CONTRACT } from "@openvibecoding/frontend-api-contract";

type ImportMetaLike = {
  env?: Record<string, unknown>;
};

type ProcessEnvCarrier = {
  process?: {
    env?: Record<string, string | undefined>;
  };
};

function readViteEnv(
  keyName: "VITE_OPENVIBECODING_API_BASE" | "VITE_OPENVIBECODING_API_TOKEN" | "VITE_OPENVIBECODING_OPERATOR_ROLE",
): string {
  const env = (import.meta as unknown as ImportMetaLike).env || {};
  const fromVite = String(env[keyName] || "").trim();
  if (fromVite) {
    return fromVite;
  }
  if (typeof globalThis === "undefined" || !("process" in globalThis)) {
    return "";
  }
  const processEnv = (globalThis as ProcessEnvCarrier).process?.env || {};
  return String(processEnv[keyName] || "").trim();
}

export function resolveDesktopApiBase(): string {
  const candidate = readViteEnv("VITE_OPENVIBECODING_API_BASE");
  if (!candidate) {
    return FRONTEND_API_CONTRACT.defaultApiBase;
  }
  return candidate.replace(/\/+$/, "");
}

export function resolveDesktopApiToken(): string {
  return readViteEnv("VITE_OPENVIBECODING_API_TOKEN");
}

export function resolveDesktopOperatorRoleEnv(): string {
  const role = readViteEnv("VITE_OPENVIBECODING_OPERATOR_ROLE");
  return role ? role.toUpperCase() : "";
}
