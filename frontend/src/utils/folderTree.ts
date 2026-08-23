import type { FolderNode } from "../types/domain";
import { isUnfiledFolder, UNFILED_FOLDER_ID } from "../types/domain";
import { appI18n } from "../i18n";

/**
 * Pure helpers for arbitrary-depth folder hierarchies (§11–§12).
 * No IO — trivially unit-testable.
 */

export interface Crumb {
  label: string;
  /** Route target when clickable; undefined for the current location. */
  to?: string;
}

export function childrenOf(folders: FolderNode[], parentId: string | null): FolderNode[] {
  return folders
    .filter((f) => f.parentId === parentId)
    .sort((a, b) => a.name.localeCompare(b.name));
}

/** Complete ancestor path from the root down to `folderId` inclusive. */
export function folderPath(
  folders: FolderNode[],
  folderId: string,
): FolderNode[] {
  const byId = new Map(folders.map((f) => [f.id, f]));
  const path: FolderNode[] = [];
  let cursor = byId.get(folderId);
  const guard = new Set<string>();
  while (cursor && !guard.has(cursor.id)) {
    guard.add(cursor.id);
    path.unshift(cursor);
    cursor = cursor.parentId ? byId.get(cursor.parentId) : undefined;
  }
  return path;
}

export function breadcrumbCrumbs(
  folders: FolderNode[],
  folderId: string,
  subjectName: string,
  subjectRoute: string,
): Crumb[] {
  const crumbs: Crumb[] = [
    { label: appI18n.t("common.breadcrumb.subjects"), to: "/subjects" },
  ];
  if (isUnfiledFolder(folderId)) {
    crumbs.push({ label: subjectName, to: subjectRoute });
    crumbs.push({ label: appI18n.t("workspace.unfiled") });
    return crumbs;
  }
  crumbs.push({ label: subjectName, to: subjectRoute });
  const chain = folderPath(folders, folderId);
  chain.forEach((node, i) => {
    const last = i === chain.length - 1;
    crumbs.push({
      label: node.name,
      ...(last ? {} : { to: `${subjectRoute}/folders/${node.id}` }),
    });
  });
  return crumbs;
}

export function descendantIds(folders: FolderNode[], folderId: string): Set<string> {
  const doomed = new Set<string>([folderId]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const f of folders) {
      if (f.parentId && doomed.has(f.parentId) && !doomed.has(f.id)) {
        doomed.add(f.id);
        grew = true;
      }
    }
  }
  return doomed;
}

/** Cycle guard: would placing `folderId` under `newParent` create a loop?
 *  A cycle occurs exactly when newParent sits inside folderId's subtree. */
export function wouldCycle(
  folders: FolderNode[],
  folderId: string,
  newParent: string | null,
): boolean {
  if (!newParent) return false;
  return descendantIds(folders, folderId).has(newParent);
}

export function countNotesRecursive(
  folders: FolderNode[],
  folderId: string,
  noteFolderByFolderId: Map<string, number>,
): number {
  let total = noteFolderByFolderId.get(folderId) ?? 0;
  for (const child of childrenOf(folders, folderId)) {
    total += countNotesRecursive(folders, child.id, noteFolderByFolderId);
  }
  return total;
}

export const UNFILED_ID = UNFILED_FOLDER_ID;
