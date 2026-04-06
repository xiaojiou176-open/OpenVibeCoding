export type SafeLoadResult<T> = {
  data: T;
  warning: string | null;
};

export async function safeLoad<T>(loader: () => Promise<T>, fallback: T, label: string): Promise<SafeLoadResult<T>> {
  try {
    return { data: await loader(), warning: null };
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    console.error(`[safeLoad] ${label} load failed: ${detail}`);
    return {
      data: fallback,
      warning: `${label} is temporarily unavailable. Try again later.`,
    };
  }
}
