function waitForChildExit(child, timeoutMs) {
  return new Promise((resolveExit) => {
    if (!child || child.exitCode !== null || child.signalCode !== null) {
      resolveExit(true);
      return;
    }
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      resolveExit(value);
    };
    const timer = setTimeout(() => finish(false), timeoutMs);
    child.once("close", () => {
      clearTimeout(timer);
      finish(true);
    });
  });
}

export async function terminateTrackedChild(child, timeoutMs = 8000) {
  if (!child) return "missing_child";
  if (child.exitCode !== null || child.signalCode !== null) return "already_exited";
  if (!Number.isInteger(child.pid) || child.pid <= 0) return "invalid_pid";

  try {
    child.kill("SIGTERM");
  } catch {
    return "term_failed";
  }
  if (await waitForChildExit(child, timeoutMs)) {
    return "SIGTERM";
  }

  try {
    child.kill("SIGKILL");
  } catch {
    return "kill_failed";
  }
  if (await waitForChildExit(child, 3000)) {
    return "SIGKILL";
  }
  return "still_running";
}
