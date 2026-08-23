import type { StrokeRecord } from "../../db/indexeddb/db";

export type ToolId = "pen" | "highlighter" | "eraser";

export const PEN_COLORS = ["#1d2433", "#2450b8", "#b8362c"] as const;
export const TOOL_SIZES = [
  { id: "fine", pen: 2, highlighter: 12 },
  { id: "medium", pen: 3.5, highlighter: 18 },
  { id: "bold", pen: 5.5, highlighter: 26 },
] as const;

/**
 * Ink rendering shared by the writer (live) and the handwritten viewer
 * (replay). Pressure modulates stroke width; highlighter is translucent.
 */

export function drawSegment(
  ctx: CanvasRenderingContext2D,
  stroke: Pick<StrokeRecord, "tool" | "color" | "width">,
  x1: number,
  y1: number,
  x2: number,
  y2: number,
): void {
  ctx.strokeStyle = stroke.color ?? "#1d2433";
  if ((stroke.tool ?? "pen") === "highlighter") {
    ctx.globalAlpha = 0.32;
    ctx.lineWidth = Math.max(stroke.width ?? 18, 10);
    ctx.lineCap = "butt";
    ctx.lineJoin = "round";
  } else {
    ctx.globalAlpha = 1;
    ctx.lineWidth = Math.max(stroke.width ?? 2.4, 0.6);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
  }
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.stroke();
  ctx.globalAlpha = 1;
}

/** Full-stroke render with pressure-based width modulation. */
export function drawStroke(ctx: CanvasRenderingContext2D, stroke: StrokeRecord): void {
  const pts = stroke.points;
  if (pts.length < 4) return;
  const pressures = stroke.pressures;
  const baseWidth = stroke.width ?? (stroke.tool === "highlighter" ? 18 : 2.4);

  for (let i = 2; i + 1 < pts.length; i += 2) {
    const t = i / 2 / (pts.length / 2 - 1);
    const p =
      pressures && pressures.length > 0
        ? pressures[Math.min(pressures.length - 1, Math.round(t * (pressures.length - 1)))]
        : 0.75;
    const width =
      stroke.tool === "highlighter"
        ? baseWidth
        : Math.max(0.6, baseWidth * (0.55 + p * 0.9));
    ctx.strokeStyle = stroke.color ?? "#1d2433";
    ctx.globalAlpha = stroke.tool === "highlighter" ? 0.32 : 1;
    ctx.lineWidth = width;
    ctx.lineCap = stroke.tool === "highlighter" ? "butt" : "round";
    ctx.beginPath();
    ctx.moveTo(pts[i - 2], pts[i - 1]);
    ctx.lineTo(pts[i], pts[i + 1]);
    ctx.stroke();
  }
  ctx.globalAlpha = 1;
}

/** Distance from point to segment — used by the eraser hit test. */
export function distToSegment(
  px: number,
  py: number,
  x1: number,
  y1: number,
  x2: number,
  y2: number,
): number {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const lengthSq = dx * dx + dy * dy;
  let t = lengthSq === 0 ? 0 : ((px - x1) * dx + (py - y1) * dy) / lengthSq;
  t = Math.max(0, Math.min(1, t));
  const cx = x1 + t * dx;
  const cy = y1 + t * dy;
  return Math.hypot(px - cx, py - cy);
}

export function strokeNear(
  stroke: StrokeRecord,
  px: number,
  py: number,
  radius: number,
): boolean {
  const pts = stroke.points;
  for (let i = 0; i + 3 < pts.length; i += 2) {
    if (distToSegment(px, py, pts[i], pts[i + 1], pts[i + 2], pts[i + 3]) <= radius) {
      return true;
    }
  }
  return false;
}
