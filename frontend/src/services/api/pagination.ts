/**
 * Defensive list helpers for the StudyAPI's DRF pagination.
 *
 * Some endpoints return `{count, next, previous, results}` while a few
 * older paths return bare arrays; both are accepted here so the UI keeps
 * working across backend revisions.
 */

import { apiRequest } from "./client";

export interface Paginated<T> {
  count?: number;
  next?: string | null;
  previous?: string | null;
  results: T[];
}

export function isPaginated<T>(value: unknown): value is Paginated<T> {
  return (
    typeof value === "object" &&
    value !== null &&
    Array.isArray((value as Paginated<T>).results)
  );
}

/** Normalize one response payload into an array. */
export function toList<T>(payload: unknown): T[] {
  if (isPaginated<T>(payload)) return payload.results;
  if (Array.isArray(payload)) return payload as T[];
  return [];
}

const MAX_PAGES = 20;

/** Follow DRF `next` links until exhausted (bounded for safety). */
export async function listAll<T>(firstPath: string): Promise<T[]> {
  const out: T[] = [];
  let path: string | null = firstPath;
  let pages = 0;
  while (path && pages < MAX_PAGES) {
    const payload: unknown = await apiRequest<unknown>(path);
    out.push(...toList<T>(payload));
    if (isPaginated<T>(payload)) {
      path = relativeNext(payload.next ?? null);
    } else {
      path = null;
    }
    pages += 1;
  }
  return out;
}

function relativeNext(next: string | null): string | null {
  if (!next) return null;
  try {
    const url = new URL(next, window.location.origin);
    return `${url.pathname}${url.search}`;
  } catch {
    return null;
  }
}
