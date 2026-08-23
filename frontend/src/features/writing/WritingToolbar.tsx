import { useTranslation } from "react-i18next";
import { PEN_COLORS, TOOL_SIZES, type ToolId } from "./ink";
import { EraserIcon, HighlighterIcon, PenIcon, RedoIcon, UndoIcon } from "../../components/ui/icons";

export interface ToolbarState {
  tool: ToolId;
  color: string;
  sizeIndex: number;
  canUndo: boolean;
  canRedo: boolean;
}

interface Props {
  state: ToolbarState;
  onTool: (tool: ToolId) => void;
  onColor: (color: string) => void;
  onSize: (index: number) => void;
  onUndo: () => void;
  onRedo: () => void;
}

/** Writer toolbar (§21): pen / highlighter / eraser, colors, sizes, undo/redo. */
export function WritingToolbar({ state, onTool, onColor, onSize, onUndo, onRedo }: Props) {
  const { t } = useTranslation();
  const toolLabels = {
    pen: t("writer.tools.pen"),
    highlighter: t("writer.tools.highlighter"),
    eraser: t("writer.tools.eraser"),
  } as const;
  return (
    <div className="writer-toolbar" role="toolbar" aria-label={t("writer.toolsAria")}>
      <div className="writer-toolbar__group">
        <ToolButton
          id="pen"
          active={state.tool === "pen"}
          label={toolLabels.pen}
          onClick={() => onTool("pen")}
        >
          <PenIcon size={15} />
        </ToolButton>
        <ToolButton
          id="highlighter"
          active={state.tool === "highlighter"}
          label={toolLabels.highlighter}
          onClick={() => onTool("highlighter")}
        >
          <HighlighterIcon size={15} />
        </ToolButton>
        <ToolButton
          id="eraser"
          active={state.tool === "eraser"}
          label={toolLabels.eraser}
          onClick={() => onTool("eraser")}
        >
          <EraserIcon size={15} />
        </ToolButton>
      </div>

      {state.tool !== "eraser" && (
        <>
          <div className="writer-toolbar__group" role="radiogroup" aria-label={t("writer.tools.colorGroup")}>
            {PEN_COLORS.map((color) => (
              <button
                key={color}
                type="button"
                role="radio"
                aria-checked={state.color === color}
                aria-label={t("writer.tools.colorAria", { color })}
                className={state.color === color ? "swatch selected" : "swatch"}
                style={{ background: color }}
                onClick={() => onColor(color)}
              />
            ))}
          </div>

          <div className="writer-toolbar__group" role="radiogroup" aria-label={t("writer.tools.sizeGroup")}>
            {TOOL_SIZES.map((size, i) => (
              <button
                key={size.id}
                type="button"
                role="radio"
                aria-checked={state.sizeIndex === i}
                aria-label={t(`writer.tools.stroke${size.id[0].toUpperCase()}${size.id.slice(1)}`)}
                className={state.sizeIndex === i ? "tool-btn active" : "tool-btn"}
                onClick={() => onSize(i)}
              >
                <span
                  aria-hidden
                  style={{
                    display: "block",
                    borderRadius: "50%",
                    background: "currentColor",
                    width: 4 + i * 4,
                    height: 4 + i * 4,
                  }}
                />
              </button>
            ))}
          </div>
        </>
      )}

      <div className="writer-toolbar__group">
        <ToolButton id="undo" active={false} label={t("writer.tools.undo")} onClick={onUndo} disabled={!state.canUndo}>
          <UndoIcon size={15} />
        </ToolButton>
        <ToolButton id="redo" active={false} label={t("writer.tools.redo")} onClick={onRedo} disabled={!state.canRedo}>
          <RedoIcon size={15} />
        </ToolButton>
      </div>
    </div>
  );
}

function ToolButton({
  id,
  active,
  label,
  onClick,
  disabled,
  children,
}: {
  id: string;
  active: boolean;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  void id;
  return (
    <button
      type="button"
      className={active ? "tool-btn active" : "tool-btn"}
      onClick={onClick}
      disabled={disabled}
      data-tip={label}
      aria-label={label}
    >
      {children}
    </button>
  );
}
