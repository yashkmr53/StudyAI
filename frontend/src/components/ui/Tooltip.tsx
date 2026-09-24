import React, {
  createContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

export type TooltipPlacement = "top" | "bottom";

export interface TooltipPositionResult {
  top: number;
  left: number;
  placement: TooltipPlacement;
  arrowOffset: number;
}

/**
 * Calculates collision-free viewport positioning for tooltips.
 * Flips top <-> bottom when space is insufficient, and clamps
 * horizontal coordinate so the full tooltip stays inside the viewport.
 */
export function computeTooltipPosition(
  targetRect: DOMRect,
  tooltipRect: { width: number; height: number },
  preferredPlacement: TooltipPlacement = "top",
  viewportPadding = 8,
  gap = 7
): TooltipPositionResult {
  const vWidth = typeof window !== "undefined" ? window.innerWidth : 1280;
  const vHeight = typeof window !== "undefined" ? window.innerHeight : 800;

  let placement = preferredPlacement;

  // Space available above and below the target
  const spaceAbove = targetRect.top - gap - viewportPadding;
  const spaceBelow = vHeight - targetRect.bottom - gap - viewportPadding;

  // Vertical collision & flipping
  if (placement === "top") {
    if (spaceAbove < tooltipRect.height) {
      if (spaceBelow >= tooltipRect.height || spaceBelow > spaceAbove) {
        placement = "bottom";
      }
    }
  } else if (placement === "bottom") {
    if (spaceBelow < tooltipRect.height) {
      if (spaceAbove >= tooltipRect.height || spaceAbove > spaceBelow) {
        placement = "top";
      }
    }
  }

  // Calculate vertical coordinate
  let top: number;
  if (placement === "top") {
    top = targetRect.top - tooltipRect.height - gap;
  } else {
    top = targetRect.bottom + gap;
  }

  // Clamp vertical coordinate so tooltip never escapes viewport
  top = Math.max(
    viewportPadding,
    Math.min(vHeight - tooltipRect.height - viewportPadding, top)
  );

  // Horizontal positioning: default to center aligned
  const targetCenter = targetRect.left + targetRect.width / 2;
  let left = targetCenter - tooltipRect.width / 2;

  // Clamp horizontal coordinate inside viewport
  const minLeft = viewportPadding;
  const maxLeft = Math.max(minLeft, vWidth - tooltipRect.width - viewportPadding);
  left = Math.max(minLeft, Math.min(maxLeft, left));

  // Arrow offset relative to tooltip left edge
  const arrowCenter = targetCenter - left;
  const minArrow = 10;
  const maxArrow = Math.max(minArrow, tooltipRect.width - 10);
  const arrowOffset = Math.max(minArrow, Math.min(maxArrow, arrowCenter));

  return {
    top,
    left,
    placement,
    arrowOffset,
  };
}

interface ActiveTooltip {
  target: HTMLElement;
  text: string;
  preferredPlacement: TooltipPlacement;
}

const TooltipContext = createContext<null>(null);

/**
 * Shared TooltipProvider:
 * Listens to hover (`pointerover`/`pointerout`) and keyboard focus (`focusin`/`focusout`)
 * for any element with `[data-tip]`, performs collision detection against all 4 viewport
 * boundaries, and renders a floating portal tooltip.
 */
export function TooltipProvider({ children }: { children: ReactNode }) {
  const [active, setActive] = useState<ActiveTooltip | null>(null);
  const [coords, setCoords] = useState<TooltipPositionResult | null>(null);
  const tooltipRef = useRef<HTMLDivElement | null>(null);
  const activeTargetRef = useRef<HTMLElement | null>(null);

  // Update position based on target and tooltip bounding rect
  const updatePosition = () => {
    const target = activeTargetRef.current;
    const tooltipEl = tooltipRef.current;
    if (!target || !target.isConnected || !tooltipEl) return;

    const targetRect = target.getBoundingClientRect();
    // If target has zero dimensions or is completely offscreen
    if (
      targetRect.width === 0 &&
      targetRect.height === 0 &&
      targetRect.top === 0 &&
      targetRect.left === 0
    ) {
      return;
    }

    const preferred = (target.getAttribute("data-tip-pos") as TooltipPlacement) || "top";
    const tipWidth = tooltipEl.offsetWidth || 120;
    const tipHeight = tooltipEl.offsetHeight || 26;

    const pos = computeTooltipPosition(
      targetRect,
      { width: tipWidth, height: tipHeight },
      preferred
    );
    setCoords(pos);
  };

  // Recalculate on active change or layout updates
  useEffect(() => {
    if (!active) {
      setCoords(null);
      return;
    }

    activeTargetRef.current = active.target;
    // Initial calculation in next animation frame once rendered
    const rafId = requestAnimationFrame(() => {
      updatePosition();
    });

    const handleScrollOrResize = () => {
      updatePosition();
    };

    window.addEventListener("scroll", handleScrollOrResize, true);
    window.addEventListener("resize", handleScrollOrResize);

    return () => {
      cancelAnimationFrame(rafId);
      window.removeEventListener("scroll", handleScrollOrResize, true);
      window.removeEventListener("resize", handleScrollOrResize);
    };
  }, [active]);

  // Global event delegation for pointer & focus
  useEffect(() => {
    function getTipTarget(node: EventTarget | null): HTMLElement | null {
      if (!(node instanceof Element)) return null;
      return node.closest<HTMLElement>("[data-tip]");
    }

    function showTooltip(el: HTMLElement) {
      const text = el.getAttribute("data-tip")?.trim();
      if (!text) {
        setActive(null);
        return;
      }
      const preferredPlacement =
        (el.getAttribute("data-tip-pos") as TooltipPlacement) || "top";
      setActive({ target: el, text, preferredPlacement });
    }

    function hideTooltip(el?: HTMLElement) {
      setActive((current) => {
        if (!el || current?.target === el) {
          return null;
        }
        return current;
      });
    }

    function onPointerOver(e: PointerEvent) {
      // Ignore simulated mouse events from touch
      if (e.pointerType === "touch") return;
      const target = getTipTarget(e.target);
      if (target) {
        showTooltip(target);
      }
    }

    function onPointerOut(e: PointerEvent) {
      const target = getTipTarget(e.target);
      const related = getTipTarget(e.relatedTarget);
      if (target && target !== related) {
        hideTooltip(target);
      }
    }

    function onFocusIn(e: FocusEvent) {
      const target = getTipTarget(e.target);
      if (target) {
        showTooltip(target);
      }
    }

    function onFocusOut(e: FocusEvent) {
      const target = getTipTarget(e.target);
      if (target) {
        hideTooltip(target);
      }
    }

    function onDismiss() {
      hideTooltip();
    }

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        hideTooltip();
      }
    }

    document.addEventListener("pointerover", onPointerOver, true);
    document.addEventListener("pointerout", onPointerOut, true);
    document.addEventListener("focusin", onFocusIn, true);
    document.addEventListener("focusout", onFocusOut, true);
    document.addEventListener("pointerdown", onDismiss, true);
    document.addEventListener("keydown", onKeyDown, true);

    return () => {
      document.removeEventListener("pointerover", onPointerOver, true);
      document.removeEventListener("pointerout", onPointerOut, true);
      document.removeEventListener("focusin", onFocusIn, true);
      document.removeEventListener("focusout", onFocusOut, true);
      document.removeEventListener("pointerdown", onDismiss, true);
      document.removeEventListener("keydown", onKeyDown, true);
    };
  }, []);

  return (
    <TooltipContext.Provider value={null}>
      {children}
      {active && (
        <div
          ref={tooltipRef}
          role="tooltip"
          id="app-tooltip"
          className={`floating-tooltip floating-tooltip--${
            coords?.placement || active.preferredPlacement
          }`}
          style={{
            top: coords ? `${coords.top}px` : "-9999px",
            left: coords ? `${coords.left}px` : "-9999px",
            visibility: coords ? "visible" : "hidden",
          }}
        >
          {active.text}
          {coords && (
            <span
              className="floating-tooltip__arrow"
              style={{
                left: `${coords.arrowOffset}px`,
                [coords.placement === "bottom" ? "top" : "bottom"]: "-4px",
                transform: "translateX(-50%) rotate(45deg)",
              }}
              aria-hidden="true"
            />
          )}
        </div>
      )}
    </TooltipContext.Provider>
  );
}

/**
 * Declarative Tooltip wrapper component for JSX elements.
 */
export function Tooltip({
  content,
  placement = "top",
  children,
}: {
  content: string;
  placement?: TooltipPlacement;
  children: React.ReactElement<{
    "data-tip"?: string;
    "data-tip-pos"?: string;
  }>;
}) {
  return React.cloneElement(children, {
    "data-tip": content,
    "data-tip-pos": placement,
  });
}
