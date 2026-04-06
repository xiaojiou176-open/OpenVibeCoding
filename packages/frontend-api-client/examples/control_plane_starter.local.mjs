import { pathToFileURL } from "node:url";

import { createControlPlaneStarter, createDashboardApiClient } from "../index.js";

function parseArgs(argv = process.argv.slice(2)) {
  const options = {
    baseUrl: "http://127.0.0.1:10000",
    role: "WORKER",
    mutationRole: "TECH_LEAD",
    previewProvider: "",
    previewModel: "",
    apply: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const raw = argv[index];
    if (raw === "--apply") {
      options.apply = true;
      continue;
    }
    const next = argv[index + 1];
    if (typeof next !== "string") {
      continue;
    }
    switch (raw) {
      case "--base-url":
        options.baseUrl = next.trim() || options.baseUrl;
        index += 1;
        break;
      case "--role":
        options.role = next.trim() || options.role;
        index += 1;
        break;
      case "--mutation-role":
        options.mutationRole = next.trim() || options.mutationRole;
        index += 1;
        break;
      case "--preview-provider":
        options.previewProvider = next.trim();
        index += 1;
        break;
      case "--preview-model":
        options.previewModel = next.trim();
        index += 1;
        break;
      default:
        break;
    }
  }

  return options;
}

function buildPreviewPayload(options) {
  const provider = options.previewProvider.trim();
  const model = options.previewModel.trim();
  if (!provider && !model) {
    return null;
  }
  return {
    runtime_binding: {
      provider: provider || null,
      model: model || null,
    },
  };
}

export async function runControlPlaneStarterExample({
  baseUrl = "http://127.0.0.1:10000",
  role = "WORKER",
  mutationRole = "TECH_LEAD",
  previewPayload = null,
  apply = false,
  resolveToken,
  fetchImpl,
} = {}) {
  const normalizedRole = role.trim() || "WORKER";
  const client = createDashboardApiClient({
    baseUrl,
    fetchImpl,
    resolveToken,
    resolveMutationRole: () => mutationRole,
  });
  const starter = createControlPlaneStarter(client);
  const bootstrap = await starter.fetchBootstrap({ role: normalizedRole });
  const preview = previewPayload
    ? await starter.previewRoleDefaults(normalizedRole, previewPayload)
    : null;
  const applied = apply && previewPayload
    ? await starter.applyRoleDefaults(normalizedRole, previewPayload)
    : null;

  return {
    role: normalizedRole,
    baseUrl,
    bootstrap,
    preview,
    applied,
    boundary: {
      starter_surface: "repo-owned-control-plane-starter",
      mcp_boundary: "read-only",
      execution_authority: "task_contract",
      apply_supported_via_client: true,
      note: "This starter defaults to bootstrap + preview. Pass --apply only when you intentionally want to persist repo-owned role defaults under the same operator policy.",
    },
  };
}

function isDirectRun() {
  const currentArg = process.argv[1];
  if (!currentArg) {
    return false;
  }
  return import.meta.url === pathToFileURL(currentArg).href;
}

if (isDirectRun()) {
  const options = parseArgs();
  const previewPayload = buildPreviewPayload(options);
  const result = await runControlPlaneStarterExample({
    baseUrl: options.baseUrl,
    role: options.role,
    mutationRole: options.mutationRole,
    previewPayload,
    apply: options.apply,
  });
  console.log(JSON.stringify(result, null, 2));
}
