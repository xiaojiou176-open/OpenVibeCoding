export const GENERAL_TASK_TEMPLATE = "general";

function bindingReadModelLabel(ref, bundleId, status) {
  const normalizedRef = String(ref || "").trim();
  const normalizedBundleId = String(bundleId || "").trim();
  const label = normalizedBundleId || normalizedRef || "-";
  return `${label} (${String(status || "-")})`;
}

export function formatBindingReadModelLabel(binding) {
  if (!binding) {
    return "- (-)";
  }
  return bindingReadModelLabel(
    binding.ref,
    Object.prototype.hasOwnProperty.call(binding, "bundle_id") ? binding.bundle_id : null,
    binding.status,
  );
}

export function formatRoleBindingRuntimeSummary(roleBindingSummary) {
  const runtimeSummary = roleBindingSummary?.runtime_binding?.summary;
  const runner = String(runtimeSummary?.runner || "-");
  const provider = String(runtimeSummary?.provider || "-");
  const model = String(runtimeSummary?.model || "-");
  return `${runner} / ${provider} / ${model}`;
}

export function formatRoleBindingRuntimeCapabilitySummary(roleBindingSummary) {
  const capability = roleBindingSummary?.runtime_binding?.capability;
  if (!capability) {
    return "- / -";
  }
  return `${capability.lane} / ${capability.tool_execution}`;
}

function splitTaskPackList(raw) {
  return String(raw)
    .split(/\r?\n|,/g)
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizeTaskPackFieldStringValue(field, raw) {
  if (Array.isArray(raw)) {
    return raw
      .map((item) => String(item ?? "").trim())
      .filter(Boolean)
      .join("\n");
  }
  if (raw === null || raw === undefined) {
    return "";
  }
  if (typeof raw === "number" || typeof raw === "boolean") {
    return String(raw);
  }
  if (typeof raw === "string") {
    return raw;
  }
  return field.value_codec === "integer" ? "0" : "";
}

export function getTaskPackFieldDefaultValue(field) {
  return normalizeTaskPackFieldStringValue(field, field.default_value);
}

export function findTaskPackByTemplate(taskPacks, taskTemplate) {
  const normalized = String(taskTemplate || "").trim().toLowerCase();
  if (!normalized || normalized === GENERAL_TASK_TEMPLATE) {
    return null;
  }
  return taskPacks.find((pack) => String(pack.task_template || "").trim().toLowerCase() === normalized) || null;
}

export function buildTaskPackFieldStateForPack(pack, currentValues = {}) {
  if (!pack) {
    return { ...currentValues };
  }
  const nextValues = { ...currentValues };
  for (const field of pack.input_fields || []) {
    if (!(field.field_id in nextValues)) {
      nextValues[field.field_id] = getTaskPackFieldDefaultValue(field);
    }
  }
  return nextValues;
}

export function mergeTaskPackFieldStateByTemplate(taskPacks, currentValuesByTemplate = {}) {
  const nextValuesByTemplate = { ...currentValuesByTemplate };
  for (const pack of taskPacks) {
    nextValuesByTemplate[pack.task_template] = buildTaskPackFieldStateForPack(
      pack,
      currentValuesByTemplate[pack.task_template] || {},
    );
  }
  return nextValuesByTemplate;
}

export function buildTaskPackTemplatePayload(pack, fieldValues = {}) {
  const payload = {};
  for (const field of pack.input_fields || []) {
    const rawValue = String(fieldValues[field.field_id] ?? getTaskPackFieldDefaultValue(field));
    const trimmed = rawValue.trim();
    if (!trimmed) {
      if (field.required) {
        throw new Error(`${field.label} is required`);
      }
      continue;
    }
    if (field.value_codec === "integer") {
      const parsed = Number.parseInt(trimmed, 10);
      if (!Number.isFinite(parsed)) {
        throw new Error(`${field.label} must be an integer`);
      }
      const boundedMin = typeof field.min === "number" ? Math.max(parsed, field.min) : parsed;
      const boundedValue = typeof field.max === "number" ? Math.min(boundedMin, field.max) : boundedMin;
      payload[field.field_id] = boundedValue;
      continue;
    }
    if (field.value_codec === "string_list") {
      const items = splitTaskPackList(trimmed);
      if (field.required && items.length === 0) {
        throw new Error(`${field.label} is required`);
      }
      payload[field.field_id] = items;
      continue;
    }
    payload[field.field_id] = trimmed;
  }
  return payload;
}

export function hydrateTaskPackFieldStateFromPayload(pack, templatePayload, currentValues = {}) {
  const nextValues = buildTaskPackFieldStateForPack(pack, currentValues);
  if (!pack || !templatePayload) {
    return nextValues;
  }
  for (const field of pack.input_fields || []) {
    if (!(field.field_id in templatePayload)) {
      continue;
    }
    nextValues[field.field_id] = normalizeTaskPackFieldStringValue(field, templatePayload[field.field_id]);
  }
  return nextValues;
}
