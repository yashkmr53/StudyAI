/**
 * Centralized user-facing copy for Reference-Coverage Guidance & Honest Labels (PR 3).
 *
 * Keeping all strings in one file allows easy copy edits and accessibility auditing.
 */
export const ENRICHMENT_COPY = {
  // Topic Coverage Badges
  badges: {
    sufficient: {
      label: "Reference found",
      ariaLabel: "Reference material found for this topic",
    },
    partial: {
      label: "Limited reference",
      ariaLabel: "Limited reference material found for this topic",
    },
    none: {
      label: "No reference found",
      ariaLabel: "No reference material found for this topic yet",
    },
  },

  // Per-Topic Guidance when coverage is "none"
  topicNoCoverage: {
    text: "No reference book covers this topic yet. Your notes are kept as written.",
    uploadLinkPrefix: "Add a reference book for ",
    uploadLinkDefault: "Add a reference book",
  },

  // Note-Level Coverage Summary
  summary: {
    topicsWithReference: (n: number, m: number) =>
      `${n} of ${m} topic${m === 1 ? "" : "s"} have reference material.`,
    allTopicsNone:
      "Your notes are structured, but no cited additions could be made because no matching reference books cover these topics yet.",
  },

  // Honest Labels for Additions
  additions: {
    supported: {
      label: "From your reference",
      icon: "📖",
      ariaLabel: "Supported directly by your reference material",
    },
    partial: {
      label: "Extends the reference",
      icon: "💡",
      tooltip: "This goes beyond the cited passage. Check it against your textbook.",
      ariaLabel: "Extends the reference beyond the cited passage",
    },
    possibleIssue: {
      label: "StudyAI Potential Issue",
      icon: "⚠️",
      ariaLabel: "Potential issue identified in your notes",
    },
  },

  // Reference Library Invalidation
  libraryChanged: {
    bannerTitle: "Your reference library changed since this note was enriched.",
    regenerateButton: "Regenerate",
    ariaRole: "status",
  },

  // Progress during generation
  progress: {
    title: "Enriching your notes",
    estimateText: "Enriching your notes, this takes about a minute.",
    stepPrefix: "Current step: ",
    stages: {
      load_and_gate: "Reading approved transcript lines...",
      classify: "Classifying study concepts...",
      plan: "Structuring topic outline...",
      research: (k: number, n: number) => `Researching references (${k} of ${n})...`,
      write: (k: number, n: number) => `Drafting notes (${k} of ${n})...`,
      verify: "Verifying citations and accuracy...",
      complete: "Finalizing enrichment...",
    },
  },
};
