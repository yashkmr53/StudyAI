import { describe, expect, it } from "vitest";
import { ocrKeyShape } from "../src/utils/idempotency";

describe("smoke", () => {
  it("builds idempotency keys like the backend", () => {
    expect(ocrKeyShape("p1", "abc", "v1")).toBe("ocr:p1:abc:v1");
  });
});
