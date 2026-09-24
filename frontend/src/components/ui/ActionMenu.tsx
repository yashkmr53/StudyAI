import { useState, useRef, useEffect, useCallback, useLayoutEffect, type ReactNode } from "react";
import { MoreVerticalIcon } from "./icons";

export interface ActionMenuItem {
  key: string;
  label: string;
  icon?: ReactNode;
  danger?: boolean;
  disabled?: boolean;
  onClick: () => void;
}

interface ActionMenuProps {
  items: ActionMenuItem[];
  ariaLabel?: string;
  className?: string;
  size?: number;
  align?: "auto" | "left" | "right";
}

export function ActionMenu({
  items,
  ariaLabel = "Actions",
  className,
  size = 15,
  align = "auto",
}: ActionMenuProps) {
  const [open, setOpen] = useState(false);
  const [horizontalAlign, setHorizontalAlign] = useState<"left" | "right">(
    align === "left" ? "left" : align === "right" ? "right" : "right"
  );
  const [verticalPlacement, setVerticalPlacement] = useState<"bottom" | "top">("bottom");
  const [dropdownStyle, setDropdownStyle] = useState<React.CSSProperties>({});
  const containerRef = useRef<HTMLDivElement | null>(null);

  const calculatePosition = useCallback(() => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const sidebar = document.querySelector(".sidebar");
    const isInsideSidebar = sidebar ? sidebar.contains(containerRef.current) : false;
    const sidebarRight = !isInsideSidebar && sidebar ? sidebar.getBoundingClientRect().right : 0;

    const MENU_MIN_WIDTH = 160;
    const padding = 8;
    const minAllowedLeft = isInsideSidebar ? padding : (sidebarRight + padding);
    const maxAllowedRight = window.innerWidth - padding;
    const maxAvailableWidth = Math.max(100, maxAllowedRight - minAllowedLeft);

    const style: React.CSSProperties = {
      maxWidth: `${Math.min(260, maxAvailableWidth)}px`,
      minWidth: `${Math.min(MENU_MIN_WIDTH, maxAvailableWidth)}px`,
    };

    // Horizontal alignment
    const wouldCrossSidebarIfRight = !isInsideSidebar && (rect.right - MENU_MIN_WIDTH < minAllowedLeft);
    const spaceOnRight = maxAllowedRight - rect.left;
    const spaceOnLeft = rect.right - minAllowedLeft;

    let chosenAlign: "left" | "right" = "left";
    if (align === "auto") {
      if (wouldCrossSidebarIfRight) {
        // Strictly protect the sidebar from being overlapped: open to the right
        chosenAlign = "left";
      } else if (spaceOnRight < MENU_MIN_WIDTH && spaceOnLeft >= MENU_MIN_WIDTH) {
        // Not enough room on the right, but safe to open to the left
        chosenAlign = "right";
      } else if (spaceOnRight >= MENU_MIN_WIDTH) {
        // Room on the right: open to the right
        chosenAlign = "left";
      } else {
        // Fallback: pick the side with more available clearance
        chosenAlign = spaceOnLeft < spaceOnRight ? "left" : "right";
      }
    } else {
      chosenAlign = align;
    }

    setHorizontalAlign(chosenAlign);

    // If aligning left but extending past maxAllowedRight, shift left without crossing minAllowedLeft
    if (chosenAlign === "left") {
      const estimatedWidth = Math.min(MENU_MIN_WIDTH, maxAvailableWidth);
      if (rect.left + estimatedWidth > maxAllowedRight) {
        const overflow = (rect.left + estimatedWidth) - maxAllowedRight;
        const maxShiftLeft = Math.max(0, rect.left - minAllowedLeft);
        const shift = Math.min(overflow, maxShiftLeft);
        if (shift > 0) {
          style.left = `-${shift}px`;
          style.right = "auto";
        }
      }
    } else {
      // If aligning right but extending before minAllowedLeft, shift right without crossing maxAllowedRight
      const estimatedWidth = Math.min(MENU_MIN_WIDTH, maxAvailableWidth);
      if (rect.right - estimatedWidth < minAllowedLeft) {
        const underflow = minAllowedLeft - (rect.right - estimatedWidth);
        const maxShiftRight = Math.max(0, maxAllowedRight - rect.right);
        const shift = Math.min(underflow, maxShiftRight);
        if (shift > 0) {
          style.right = `-${shift}px`;
          style.left = "auto";
        }
      }
    }

    setDropdownStyle(style);

    // Vertical placement
    const spaceBelow = window.innerHeight - rect.bottom;
    const spaceAbove = rect.top;
    const MENU_HEIGHT = 160;
    if (spaceBelow < MENU_HEIGHT && spaceAbove > spaceBelow) {
      setVerticalPlacement("top");
    } else {
      setVerticalPlacement("bottom");
    }
  }, [align]);

  useLayoutEffect(() => {
    if (open) {
      calculatePosition();
    }
  }, [open, calculatePosition]);

  useEffect(() => {
    if (!open) return;
    function handleDown(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(false);
      }
    }
    function handleResizeOrScroll() {
      calculatePosition();
    }

    document.addEventListener("mousedown", handleDown);
    document.addEventListener("keydown", handleKey);
    window.addEventListener("resize", handleResizeOrScroll);
    window.addEventListener("scroll", handleResizeOrScroll, true);
    return () => {
      document.removeEventListener("mousedown", handleDown);
      document.removeEventListener("keydown", handleKey);
      window.removeEventListener("resize", handleResizeOrScroll);
      window.removeEventListener("scroll", handleResizeOrScroll, true);
    };
  }, [open, calculatePosition]);

  return (
    <div
      ref={containerRef}
      className={`action-menu ${className ?? ""}`}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
      }}
    >
      <button
        type="button"
        className={`icon-btn ${open ? "active" : ""}`}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen((prev) => !prev);
        }}
        aria-label={ariaLabel}
        data-tip={open ? undefined : ariaLabel}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <MoreVerticalIcon size={size} />
      </button>

      {open && (
        <div
          className={`action-menu__dropdown action-menu__dropdown--align-${horizontalAlign} action-menu__dropdown--placement-${verticalPlacement}`}
          style={dropdownStyle}
          role="menu"
        >
          {items.map((item) => (
            <button
              key={item.key}
              type="button"
              role="menuitem"
              className={`action-menu__item ${item.danger ? "action-menu__item--danger" : ""}`}
              disabled={item.disabled}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                setOpen(false);
                item.onClick();
              }}
            >
              {item.icon && <span style={{ display: "inline-flex" }}>{item.icon}</span>}
              <span>{item.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

