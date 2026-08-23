import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

interface Props {
  title: string;
  description: string;
  icon: ReactNode;
  iconColor?: { bg: string; fg: string };
  to: string;
}

/** One AI capability card in the AI Classroom workspace panel (§10). */
export function ServiceCard({ title, description, icon, iconColor, to }: Props) {
  const navigate = useNavigate();
  return (
    <button type="button" className="card service-card" onClick={() => navigate(to)}>
      <span
        className="service-card__icon"
        style={{ background: iconColor?.bg ?? "#eef0fc", color: iconColor?.fg ?? "#4f5bd5" }}
      >
        {icon}
      </span>
      <span className="service-card__title">{title}</span>
      <span className="service-card__desc">{description}</span>
    </button>
  );
}
