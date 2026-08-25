/**
 * Minimal inline icon set (stroke style, 16–20px). Kept dependency-free.
 */

interface IconProps {
  size?: number;
  className?: string;
}

function base(size?: number) {
  return {
    width: size ?? 16,
    height: size ?? 16,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
}

export function FolderIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
    </svg>
  );
}

export function NoteIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M6 3h9l5 5v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z" />
      <path d="M14 3v6h6" />
      <path d="M9 13h6M9 17h4" />
    </svg>
  );
}

export function PlusIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

export function PenIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="m17 3 4 4L8 20l-5 1 1-5z" />
    </svg>
  );
}

export function HighlighterIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="m9 11 6-8 6 6-8 6z" />
      <path d="M4 20c3 1 6-1 6-4l3 2c-1 3-5 5-9 4z" />
    </svg>
  );
}

export function EraserIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="m7 21-4-4a2 2 0 0 1 0-2.8L14 3l7 7-8.8 8.8a2 2 0 0 1-2.8 0z" />
      <path d="M22 21H10" />
    </svg>
  );
}

export function UndoIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M9 14 4 9l5-5" />
      <path d="M4 9h10a6 6 0 0 1 0 12h-3" />
    </svg>
  );
}

export function RedoIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="m15 14 5-5-5-5" />
      <path d="M20 9H10a6 6 0 0 0 0 12h3" />
    </svg>
  );
}

export function TrashIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13M9 7V4h6v3" />
    </svg>
  );
}

export function ChevronRightIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="m9 6 6 6-6 6" />
    </svg>
  );
}

export function ChevronDownIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}

export function CheckIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="m4.5 12.5 5 5 10-11" />
    </svg>
  );
}

export function SparkleIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M12 3v4M12 17v4M3 12h4M17 12h4M6.3 6.3l2.5 2.5M15.2 15.2l2.5 2.5M17.7 6.3l-2.5 2.5M8.8 15.2l-2.5 2.5" />
    </svg>
  );
}

export function ChatIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M21 12a8 8 0 0 1-8 8H4l2-3a8 8 0 1 1 15-5z" />
    </svg>
  );
}

export function QuizIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M9.2 9a3 3 0 1 1 4.4 2.7c-.9.5-1.6 1.1-1.6 2.3" />
      <circle cx="12" cy="17.5" r="0.5" fill="currentColor" />
      <circle cx="12" cy="12" r="9.5" />
    </svg>
  );
}

export function ClipboardIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <rect x="5" y="4" width="14" height="17" rx="2" />
      <path d="M9 4a3 3 0 0 1 6 0M9 10h6M9 14h4" />
    </svg>
  );
}

export function BookIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5zM4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5" />
    </svg>
  );
}

export function AlertIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M12 3 2.5 20h19zM12 10v4M12 17.5v.01" />
    </svg>
  );
}

export function RefreshIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M21 12a9 9 0 1 1-2.6-6.3M21 3v6h-6" />
    </svg>
  );
}

export function DownloadIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M12 3v12M6 9l6 6 6-6" />
      <path d="M4 17h16" />
    </svg>
  );
}

export function UploadIcon({ size, className }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M12 3v12M6 9l6 6 6-6" />
      <path d="M4 17h16" />
    </svg>
  );
}
