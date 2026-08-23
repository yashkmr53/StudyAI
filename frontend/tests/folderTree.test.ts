import { describe, expect, it } from "vitest";
import type { FolderNode } from "../src/types/domain";
import {
  breadcrumbCrumbs,
  childrenOf,
  countNotesRecursive,
  descendantIds,
  folderPath,
  wouldCycle,
} from "../src/utils/folderTree";

const TREE: FolderNode[] = [
  { id: "dsa", subjectId: "s1", parentId: null, name: "DSA" },
  { id: "trees", subjectId: "s1", parentId: "dsa", name: "Trees" },
  { id: "binary", subjectId: "s1", parentId: "trees", name: "Binary Trees" },
  { id: "traversal", subjectId: "s1", parentId: "binary", name: "Traversal" },
  { id: "dfs", subjectId: "s1", parentId: "traversal", name: "DFS" },
  { id: "ml-only", subjectId: "s2", parentId: null, name: "ML" },
];

describe("folderPath (Rule 11 — arbitrary nesting)", () => {
  it("returns the full chain root→leaf at any depth", () => {
    const path = folderPath(TREE, "dfs");
    expect(path.map((f) => f.name)).toEqual(["DSA", "Trees", "Binary Trees", "Traversal", "DFS"]);
  });

  it("handles single-level folders", () => {
    expect(folderPath(TREE, "dsa").map((f) => f.id)).toEqual(["dsa"]);
  });
});

describe("childrenOf", () => {
  it("returns only direct children sorted by name", () => {
    const kids = childrenOf(
      [
        { id: "b", subjectId: "s", parentId: "root", name: "Beta" },
        { id: "a", subjectId: "s", parentId: "root", name: "Alpha" },
        { id: "c", subjectId: "s", parentId: "other", name: "Gamma" },
      ],
      "root",
    );
    expect(kids.map((k) => k.id)).toEqual(["a", "b"]);
  });
});

describe("breadcrumbCrumbs (Rule 12)", () => {
  it("emits one crumb per hierarchy level", () => {
    const crumbs = breadcrumbCrumbs(TREE, "dfs", "Data Structures", "/subjects/s1");
    expect(crumbs.map((c) => c.label)).toEqual([
      "Subjects",
      "Data Structures",
      "DSA",
      "Trees",
      "Binary Trees",
      "Traversal",
      "DFS",
    ]);
  });

  it("marks the last crumb as current and links the rest", () => {
    const crumbs = breadcrumbCrumbs(TREE, "binary", "DS", "/subjects/s1");
    expect(crumbs.at(-1)?.to).toBeUndefined();
    expect(crumbs[2]?.to).toBe("/subjects/s1/folders/dsa");
  });

  it("renders Unfiled like a normal level under the subject", () => {
    const crumbs = breadcrumbCrumbs(TREE, "__unfiled__", "DS", "/subjects/s1");
    expect(crumbs.map((c) => c.label)).toEqual(["Subjects", "DS", "Unfiled"]);
  });
});

describe("descendantIds / wouldCycle", () => {
  it("collects all descendants regardless of depth", () => {
    expect(descendantIds(TREE, "trees")).toEqual(new Set(["trees", "binary", "traversal", "dfs"]));
  });

  it("detects cycles when nesting a folder under its own child", () => {
    expect(wouldCycle(TREE, "trees", "dfs")).toBe(true);
    expect(wouldCycle(TREE, "trees", "dsa")).toBe(false);
    expect(wouldCycle(TREE, "trees", null)).toBe(false);
  });
});

describe("countNotesRecursive", () => {
  it("counts notes across nested folders", () => {
    // notes: 2 in trees, 1 in traversal
    const counts = new Map([
      ["trees", 2],
      ["traversal", 1],
    ]);
    expect(countNotesRecursive(TREE, "trees", counts)).toBe(3);
    expect(countNotesRecursive(TREE, "dsa", counts)).toBe(3);
  });
});
