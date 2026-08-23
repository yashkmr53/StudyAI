import type { Crumb } from "../../utils/folderTree";
import { ChevronRightIcon } from "../ui/icons";
import { useTranslation } from "react-i18next";

/**
 * Arbitrary-depth breadcrumbs (§12): every crumb renders from data;
 * nothing assumes a fixed hierarchy depth.
 */
export function Breadcrumbs({ crumbs }: { crumbs: Crumb[] }) {
  const { t } = useTranslation();
  return (
    <nav className="breadcrumbs" aria-label={t("common.breadcrumb.label")}>
      {crumbs.map((crumb, i) => {
        const last = i === crumbs.length - 1;
        return (
          <span key={`${crumb.label}-${i}`} className="breadcrumbs__crumb">
            {last || !crumb.to ? (
              <span className="breadcrumbs__current" aria-current={last ? "page" : undefined}>
                {crumb.label}
              </span>
            ) : (
              <span className="breadcrumbs__crumb">
                <a className="breadcrumbs__link" href={crumb.to}>
                  {crumb.label}
                </a>
              </span>
            )}
            {!last && (
              <span className="breadcrumbs__sep" aria-hidden>
                <ChevronRightIcon size={13} />
              </span>
            )}
          </span>
        );
      })}
    </nav>
  );
}
