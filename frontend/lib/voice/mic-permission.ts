/** The browser's microphone permission, when the Permissions API knows it ("granted" skips the explainer). */
export async function micPermission(): Promise<PermissionState | "unknown"> {
  try {
    return (await navigator.permissions.query({ name: "microphone" as PermissionName })).state;
  } catch {
    return "unknown";
  }
}
