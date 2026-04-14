import { afterEach, describe, expect, it } from "vitest";

import { FRONTEND_API_CONTRACT } from "../lib/frontendApiContract";
import {
  resolveDashboardApiBase,
  resolveDashboardOperatorRoleEnv,
  resolveDashboardPmCopyVariantEnv,
  resolveDashboardPublicDocsBaseUrl,
  resolveDashboardPublicDocsHref,
} from "../lib/env";

const ORIGINAL_API_BASE = process.env.NEXT_PUBLIC_API_BASE;
const ORIGINAL_OPENVIBECODING_API_BASE = process.env.NEXT_PUBLIC_OPENVIBECODING_API_BASE;
const ORIGINAL_OPENVIBECODING_PUBLIC_DOCS_BASE_URL = process.env.NEXT_PUBLIC_OPENVIBECODING_PUBLIC_DOCS_BASE_URL;
const ORIGINAL_OPENVIBECODING_OPERATOR_ROLE = process.env.NEXT_PUBLIC_OPENVIBECODING_OPERATOR_ROLE;
const ORIGINAL_PM_COPY_VARIANT = process.env.NEXT_PUBLIC_PM_COPY_VARIANT;

function restoreEnv(): void {
  if (ORIGINAL_API_BASE === undefined) delete process.env.NEXT_PUBLIC_API_BASE;
  else process.env.NEXT_PUBLIC_API_BASE = ORIGINAL_API_BASE;

  if (ORIGINAL_OPENVIBECODING_API_BASE === undefined) delete process.env.NEXT_PUBLIC_OPENVIBECODING_API_BASE;
  else process.env.NEXT_PUBLIC_OPENVIBECODING_API_BASE = ORIGINAL_OPENVIBECODING_API_BASE;

  if (ORIGINAL_OPENVIBECODING_PUBLIC_DOCS_BASE_URL === undefined) delete process.env.NEXT_PUBLIC_OPENVIBECODING_PUBLIC_DOCS_BASE_URL;
  else process.env.NEXT_PUBLIC_OPENVIBECODING_PUBLIC_DOCS_BASE_URL = ORIGINAL_OPENVIBECODING_PUBLIC_DOCS_BASE_URL;

  if (ORIGINAL_OPENVIBECODING_OPERATOR_ROLE === undefined) delete process.env.NEXT_PUBLIC_OPENVIBECODING_OPERATOR_ROLE;
  else process.env.NEXT_PUBLIC_OPENVIBECODING_OPERATOR_ROLE = ORIGINAL_OPENVIBECODING_OPERATOR_ROLE;

  if (ORIGINAL_PM_COPY_VARIANT === undefined) delete process.env.NEXT_PUBLIC_PM_COPY_VARIANT;
  else process.env.NEXT_PUBLIC_PM_COPY_VARIANT = ORIGINAL_PM_COPY_VARIANT;
}

describe("dashboard env helpers", () => {
  afterEach(() => {
    restoreEnv();
  });

  it("prefers NEXT_PUBLIC_OPENVIBECODING_API_BASE and trims trailing slashes", () => {
    process.env.NEXT_PUBLIC_OPENVIBECODING_API_BASE = " https://openvibecoding.example/api/// ";
    process.env.NEXT_PUBLIC_API_BASE = "https://fallback.example";

    expect(resolveDashboardApiBase()).toBe("https://openvibecoding.example/api");
  });

  it("falls back to NEXT_PUBLIC_API_BASE when the product-specific env is absent", () => {
    process.env.NEXT_PUBLIC_API_BASE = "https://fallback.example";

    expect(resolveDashboardApiBase()).toBe("https://fallback.example");
  });

  it("falls back to NEXT_PUBLIC_API_BASE when the preferred env is blank", () => {
    process.env.NEXT_PUBLIC_OPENVIBECODING_API_BASE = "   ";
    process.env.NEXT_PUBLIC_API_BASE = "https://fallback.example/base//";

    expect(resolveDashboardApiBase()).toBe("https://fallback.example/base");
  });

  it("uses the frontend contract default when both env values are absent", () => {
    delete process.env.NEXT_PUBLIC_OPENVIBECODING_API_BASE;
    delete process.env.NEXT_PUBLIC_API_BASE;

    expect(resolveDashboardApiBase()).toBe(FRONTEND_API_CONTRACT.defaultApiBase);
  });

  it("falls through to the final default return when every candidate is empty", () => {
    delete process.env.NEXT_PUBLIC_OPENVIBECODING_API_BASE;
    delete process.env.NEXT_PUBLIC_API_BASE;
    const previousDefault = FRONTEND_API_CONTRACT.defaultApiBase;
    try {
      (FRONTEND_API_CONTRACT as { defaultApiBase: string }).defaultApiBase = "";
      expect(resolveDashboardApiBase()).toBe("");
    } finally {
      (FRONTEND_API_CONTRACT as { defaultApiBase: string }).defaultApiBase = previousDefault;
    }
  });

  it("returns the PM copy variant verbatim after trimming", () => {
    process.env.NEXT_PUBLIC_PM_COPY_VARIANT = " b ";

    expect(resolveDashboardPmCopyVariantEnv()).toBe("b");
  });

  it("uses the default public docs base when the env override is absent", () => {
    delete process.env.NEXT_PUBLIC_OPENVIBECODING_PUBLIC_DOCS_BASE_URL;

    expect(resolveDashboardPublicDocsBaseUrl()).toBe("https://xiaojiou176-open.github.io/OpenVibeCoding");
    expect(resolveDashboardPublicDocsHref("/ai-surfaces/")).toBe(
      "https://xiaojiou176-open.github.io/OpenVibeCoding/ai-surfaces/"
    );
  });

  it("uses a configured public docs base and trims trailing slashes", () => {
    process.env.NEXT_PUBLIC_OPENVIBECODING_PUBLIC_DOCS_BASE_URL = " https://docs.example/openvibecoding/// ";

    expect(resolveDashboardPublicDocsBaseUrl()).toBe("https://docs.example/openvibecoding");
    expect(resolveDashboardPublicDocsHref("/builders/")).toBe("https://docs.example/openvibecoding/builders/");
    expect(resolveDashboardPublicDocsHref("/compatibility/")).toBe("https://docs.example/openvibecoding/compatibility/");
    expect(resolveDashboardPublicDocsHref("/integrations/")).toBe("https://docs.example/openvibecoding/integrations/");
    expect(resolveDashboardPublicDocsHref("/skills/")).toBe("https://docs.example/openvibecoding/skills/");
  });

  it("allows same-origin public docs routes when the override is slash", () => {
    process.env.NEXT_PUBLIC_OPENVIBECODING_PUBLIC_DOCS_BASE_URL = "/";

    expect(resolveDashboardPublicDocsBaseUrl()).toBe("");
    expect(resolveDashboardPublicDocsHref("/mcp/")).toBe("/mcp/");
  });

  it("leaves non-public-docs href values untouched", () => {
    process.env.NEXT_PUBLIC_OPENVIBECODING_PUBLIC_DOCS_BASE_URL = "https://docs.example/openvibecoding";

    expect(resolveDashboardPublicDocsHref("/pm")).toBe("/pm");
    expect(resolveDashboardPublicDocsHref("https://github.com/xiaojiou176-open/OpenVibeCoding")).toBe(
      "https://github.com/xiaojiou176-open/OpenVibeCoding"
    );
  });

  it("uses NEXT_PUBLIC_OPENVIBECODING_OPERATOR_ROLE and normalizes casing", () => {
    process.env.NEXT_PUBLIC_OPENVIBECODING_OPERATOR_ROLE = " tech_lead ";
    expect(resolveDashboardOperatorRoleEnv()).toBe("TECH_LEAD");
  });
});
