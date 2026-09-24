import { describe, expect, it } from "vitest";
import { computeTooltipPosition } from "../src/components/ui/Tooltip";

describe("Tooltip computeTooltipPosition - Viewport Boundary Collision & Flipping", () => {
  const tooltipRect = { width: 140, height: 26 };
  const viewportPadding = 8;
  const gap = 7;

  it("places tooltip ABOVE the target when sufficient space exists above", () => {
    // Target comfortably in middle of screen (1280x800)
    const targetRect = {
      top: 300,
      bottom: 332,
      left: 500,
      right: 532,
      width: 32,
      height: 32,
    } as DOMRect;

    const result = computeTooltipPosition(
      targetRect,
      tooltipRect,
      "top",
      viewportPadding,
      gap
    );

    expect(result.placement).toBe("top");
    expect(result.top).toBe(targetRect.top - tooltipRect.height - gap); // 300 - 26 - 7 = 267
    expect(result.top).toBeGreaterThanOrEqual(viewportPadding);

    // Centered horizontally
    const targetCenter = 500 + 16; // 516
    expect(result.left).toBe(targetCenter - tooltipRect.width / 2); // 516 - 70 = 446
  });

  it("automatically FLIPS to BOTTOM when space above target is insufficient (collision with top boundary)", () => {
    // Target near top edge (e.g. note editor toolbar at top: 10px)
    const targetRect = {
      top: 10,
      bottom: 38,
      left: 200,
      right: 228,
      width: 28,
      height: 28,
    } as DOMRect;

    const result = computeTooltipPosition(
      targetRect,
      tooltipRect,
      "top",
      viewportPadding,
      gap
    );

    // Must flip to bottom because spaceAbove (10 - 7 - 8 = -5) < tooltipHeight (26)
    expect(result.placement).toBe("bottom");
    expect(result.top).toBe(targetRect.bottom + gap); // 38 + 7 = 45
    expect(result.top).toBeGreaterThanOrEqual(viewportPadding);
    expect(result.top + tooltipRect.height).toBeLessThanOrEqual(800 - viewportPadding);
  });

  it("automatically FLIPS to TOP when preferred is bottom but space below is insufficient (collision with bottom boundary)", () => {
    // Target near bottom edge (e.g. at bottom: 790px)
    const targetRect = {
      top: 760,
      bottom: 792,
      left: 200,
      right: 232,
      width: 32,
      height: 32,
    } as DOMRect;

    const result = computeTooltipPosition(
      targetRect,
      tooltipRect,
      "bottom",
      viewportPadding,
      gap
    );

    // Must flip to top because spaceBelow (800 - 792 - 7 - 8 = -7) < tooltipHeight (26)
    expect(result.placement).toBe("top");
    expect(result.top).toBe(targetRect.top - tooltipRect.height - gap); // 760 - 26 - 7 = 727
    expect(result.top).toBeGreaterThanOrEqual(viewportPadding);
  });

  it("CLAMPS horizontal position when target is near the LEFT boundary", () => {
    // Target at the far left edge of screen (left: 4px)
    const targetRect = {
      top: 100,
      bottom: 132,
      left: 4,
      right: 36,
      width: 32,
      height: 32,
    } as DOMRect;

    const result = computeTooltipPosition(
      targetRect,
      tooltipRect,
      "top",
      viewportPadding,
      gap
    );

    // Normally center would be 20 - 70 = -50 (off-screen left!)
    // Must be clamped to viewportPadding (8px)
    expect(result.left).toBe(viewportPadding);
    expect(result.left + tooltipRect.width).toBeLessThanOrEqual(1280);

    // Arrow must point towards the target center (20px), clamped within bounds
    expect(result.arrowOffset).toBe(12); // targetCenter (20) - left (8) = 12
  });

  it("CLAMPS horizontal position when target is near the RIGHT boundary", () => {
    // Target at the far right edge of a 1280px screen (right: 1276px)
    const targetRect = {
      top: 100,
      bottom: 132,
      left: 1244,
      right: 1276,
      width: 32,
      height: 32,
    } as DOMRect;

    const result = computeTooltipPosition(
      targetRect,
      tooltipRect,
      "top",
      viewportPadding,
      gap
    );

    // Centered left would be 1260 - 70 = 1190, but 1190 + 140 = 1330 (off-screen right!)
    // Max left is 1280 - 140 - 8 = 1132
    expect(result.left).toBe(1280 - tooltipRect.width - viewportPadding);
    expect(result.left + tooltipRect.width).toBe(1280 - viewportPadding);

    // Arrow offset points towards the target center (1260 - 1132 = 128)
    expect(result.arrowOffset).toBe(128);
  });

  it("ensures arrowOffset remains within tooltip boundaries", () => {
    // Extreme left target where targetCenter is even smaller than padding
    const extremeLeftTarget = {
      top: 100,
      bottom: 132,
      left: 0,
      right: 10,
      width: 10,
      height: 32,
    } as DOMRect;

    const result = computeTooltipPosition(
      extremeLeftTarget,
      tooltipRect,
      "top",
      viewportPadding,
      gap
    );

    // Arrow must not poke outside the left border radius (minimum 10px)
    expect(result.arrowOffset).toBeGreaterThanOrEqual(10);
    expect(result.arrowOffset).toBeLessThanOrEqual(tooltipRect.width - 10);
  });
});
