import { DownloadIcon } from "../ui/icons";

interface ArtifactCardProps {
  title: string;
  filename: string;
  url: string;
  documentId: string;
  format: "pdf" | "pptx" | "docx";
}

export function ArtifactCard({ title, filename, url, format }: ArtifactCardProps) {
  const formatColors = {
    pdf: "bg-red-50 text-red-700 border-red-200",
    pptx: "bg-orange-50 text-orange-700 border-orange-200",
    docx: "bg-blue-50 text-blue-700 border-blue-200",
  };

  return (
    <div className={`card border ${formatColors[format]} p-3 flex items-center gap-3`}>
      <div className="grow">
        <div className="font-medium text-sm">{title || filename}</div>
        <div className="text-xs opacity-75">{format.toUpperCase()} Document</div>
      </div>
      <a
        href={url}
        download
        className="btn btn--secondary btn--sm"
        title={`Download ${format.toUpperCase()}`}
      >
        <DownloadIcon size={14} />
        Download
      </a>
    </div>
  );
}
