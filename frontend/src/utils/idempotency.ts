/** Mirrors backend shared.idempotency.keys (architecture §20). */
export function ocrKeyShape(pageId: string, contentHash: string, pipelineVersion: string): string {
  return `ocr:${pageId}:${contentHash}:${pipelineVersion}`;
}
