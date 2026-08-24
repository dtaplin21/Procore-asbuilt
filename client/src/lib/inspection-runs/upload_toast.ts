type UploadToastFields = {
  overlays_created: number;
  unresolved_count: number;
  untagged_region_count: number;
};

/** User-facing upload summary — avoids "0 overlays mapped" before match completes. */
export function formatEvidenceUploadToastDescription(
  runId: number,
  response: UploadToastFields,
): string {
  const parts: string[] = [];

  if (response.overlays_created > 0) {
    parts.push(
      `${response.overlays_created} overlay${response.overlays_created === 1 ? "" : "s"} mapped`,
    );
  } else {
    parts.push("Investigating linked files and matching location");
  }

  if (response.unresolved_count > 0) {
    parts.push(`${response.unresolved_count} need review`);
  }
  if (response.untagged_region_count > 0) {
    parts.push(`${response.untagged_region_count} untagged region(s) on sheet`);
  }

  return `Run #${runId}: ${parts.join(" · ")}`;
}
