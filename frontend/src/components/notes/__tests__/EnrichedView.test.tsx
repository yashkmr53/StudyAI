import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { EnrichedView } from "../EnrichedView";
import type { EnrichmentSnapshot, NoteMeta } from "../../../types/domain";

// Mock react-i18next
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, defaultVal?: any) => {
      const translations: Record<string, string> = {
        "notes.enriched.generatingTitle": "Generating enrichment...",
        "notes.enriched.generatingBody": "Analyzing notes and synthesizing research...",
        "notes.enriched.staleTitle": "Notes out of date",
        "notes.enriched.staleBody": "The source handwritten note was edited. Regenerate to update the enrichment.",
        "notes.enriched.regenerate": "Regenerate",
        "notes.enriched.emptyTitle": "No enrichment yet",
        "notes.enriched.emptyDescription": "Enhance your notes with textbook context.",
        "notes.enriched.generate": "Generate Enrichment",
        "notes.enriched.sourcesAria": "Sources and citations",
        "notes.enriched.citation": "Page {{page}}",
        "notes.enriched.generatedAt": "Generated on {{date}}",
      };
      let result = typeof defaultVal === "string" ? defaultVal : (translations[key] || key);
      if (typeof defaultVal === "object" && defaultVal !== null) {
        for (const [k, v] of Object.entries(defaultVal)) {
          result = result.replace(`{{${k}}}`, String(v));
        }
      }
      return result;
    },
  }),
}));

// Mock APIs called on mount
vi.mock("../../../services/api/enrichment", () => ({
  enrichmentApi: {
    get: vi.fn(),
    generate: vi.fn(),
    getJob: vi.fn(),
    forceInclude: vi.fn(),
  },
  parseEnrichment: vi.fn(),
}));

vi.mock("../../../services/api/documents", () => ({
  documentsApi: {
    pages: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock("../../../services/api/tags", () => ({
  tagsApi: {
    list: vi.fn().mockResolvedValue([]),
  },
}));

describe("EnrichedView Component Visual Styling & Rendering Tests", () => {
  const mockNote: NoteMeta = {
    id: "note-123",
    refId: "doc-123",
    documentId: "doc-123",
    profileId: "prof-123",
    subjectId: "sub-123",
    folderId: "f-1",
    title: "Operating Systems Memory Management",
    source: "upload",
    createdAt: "2026-10-30T10:00:00Z",
    updatedAt: "2026-10-30T10:00:00Z",
  };

  it("renders student prose and code blocks with distinct typography and styling", () => {
    const snapshot: EnrichmentSnapshot = {
      state: "enriched",
      generatedAt: "2026-10-30T10:00:00Z",
      blocks: [
        {
          index: 0,
          title: "Virtual Memory",
          content: "Virtual Memory",
          blockKind: "heading",
          renderAs: "prose",
          citations: [],
        },
        {
          index: 1,
          title: "",
          content: "Virtual memory maps virtual addresses to physical frames via page tables.",
          blockKind: "student",
          renderAs: "prose",
          citations: [],
        },
        {
          index: 2,
          title: "",
          content: "uint32_t page_number = virtual_addr >> 12;",
          blockKind: "student",
          renderAs: "code",
          citations: [],
        },
      ],
    };

    const html = renderToStaticMarkup(
      <MemoryRouter>
        <EnrichedView note={mockNote} onCitation={vi.fn()} initialSnapshot={snapshot} />
      </MemoryRouter>,
    );

    // Assert student blocks have class 'student-block'
    expect(html).toContain("student-block");

    // Prose student block has paragraph and proper color styling
    expect(html).toContain("Virtual memory maps virtual addresses to physical frames");
    expect(html).toContain('color:#374151');

    // Code student block renders inside pre/code tag
    expect(html).toContain("<pre");
    expect(html).toContain("<code");
    expect(html).toContain("uint32_t page_number = virtual_addr &gt;&gt; 12;");
  });

  it("renders normal addition blocks and possible_issue blocks with distinguishing visual styling", () => {
    const snapshot: EnrichmentSnapshot = {
      state: "enriched",
      generatedAt: "2026-10-30T10:00:00Z",
      blocks: [
        {
          index: 0,
          title: "",
          content: "The Translation Lookaside Buffer (TLB) caches recent translations to reduce page walks.",
          blockKind: "addition",
          additionKind: "elaboration",
          renderAs: "prose",
          citations: [
            {
              page: 142,
              sourceType: "reference",
            },
          ],
        },
        {
          index: 1,
          title: "",
          content: "Note: Inverted page tables do not eliminate memory overhead entirely.",
          blockKind: "addition",
          additionKind: "possible_issue",
          renderAs: "prose",
          citations: [
            {
              page: 145,
              sourceType: "reference",
            },
          ],
        },
      ],
    };

    const html = renderToStaticMarkup(
      <MemoryRouter>
        <EnrichedView note={mockNote} onCitation={vi.fn()} initialSnapshot={snapshot} />
      </MemoryRouter>,
    );

    // Assert both blocks are rendered as aside.addition-block
    expect(html).toContain("addition-block");

    // Standard addition styling (blue accent)
    expect(html).toContain("✨ StudyAI Note");
    expect(html).toContain("background:#f0f4ff");
    expect(html).toContain("border-left:4px solid #4f5bd5");
    expect(html).toContain("The Translation Lookaside Buffer (TLB) caches recent translations");

    // Possible issue styling (amber accent)
    expect(html).toContain("⚠️ StudyAI Potential Issue");
    expect(html).toContain("background:#fffbeb");
    expect(html).toContain("border-left:4px solid #f59e0b");
    expect(html).toContain("Note: Inverted page tables do not eliminate memory overhead");

    // Reference citations rendered with Ref chip
    expect(html).toContain("📖 Ref: p. 142");
    expect(html).toContain("📖 Ref: p. 145");
  });

  it("renders out-of-date stale banner with regenerate trigger when state is out_of_date", () => {
    const snapshot: EnrichmentSnapshot = {
      state: "out_of_date",
      generatedAt: "2026-10-30T09:00:00Z",
      blocks: [
        {
          index: 0,
          title: "",
          content: "Original student note line",
          blockKind: "student",
          renderAs: "prose",
          citations: [],
        },
      ],
    };

    const html = renderToStaticMarkup(
      <MemoryRouter>
        <EnrichedView note={mockNote} onCitation={vi.fn()} initialSnapshot={snapshot} />
      </MemoryRouter>,
    );

    // Assert stale banner is displayed
    expect(html).toContain('class="stale-note"');
    expect(html).toContain('role="alert"');
    expect(html).toContain("Notes out of date");
    expect(html).toContain("The source handwritten note was edited. Regenerate to update the enrichment.");

    // Contains regenerate button
    expect(html).toContain("Regenerate");
    expect(html).toContain("btn--secondary");
  });

  it("renders legacy blocks when blockKind is not heading/student/addition", () => {
    const snapshot: EnrichmentSnapshot = {
      state: "enriched",
      generatedAt: "2026-10-30T10:00:00Z",
      blocks: [
        {
          index: 0,
          title: "Key Takeaways",
          content: "Demand paging brings pages into memory only when they are referenced.",
          citations: [
            {
              page: 1,
              sourceType: "image",
            },
          ],
        } as any,
      ],
    };

    const html = renderToStaticMarkup(
      <MemoryRouter>
        <EnrichedView note={mockNote} onCitation={vi.fn()} initialSnapshot={snapshot} />
      </MemoryRouter>,
    );

    // Assert legacy section with enriched-block class is rendered
    expect(html).toContain('class="enriched-block"');
    expect(html).toContain('class="enriched-block__title"');
    expect(html).toContain("Key Takeaways");
    expect(html).toContain('class="enriched-block__content"');
    expect(html).toContain("Demand paging brings pages into memory only when they are referenced.");

    // Student note citation chip
    expect(html).toContain("📝 Page 1");
  });

  it("renders per-topic coverage badges, note summary, and none guidance link (PR 3 §3.1)", () => {
    const snapshot: EnrichmentSnapshot = {
      state: "enriched",
      generatedAt: "2026-10-30T10:00:00Z",
      subjectId: "sub-cs-1",
      subjectName: "Computer Science",
      evidenceStatusByTopic: {
        t1: "sufficient",
        t2: "partial",
        t3: "none",
      },
      blocks: [
        {
          index: 0,
          title: "Virtual Memory Architecture",
          content: "Virtual Memory Architecture",
          blockKind: "heading",
          topicId: "t1",
          citations: [],
        },
        {
          index: 1,
          title: "Page Replacement Algorithms",
          content: "Page Replacement Algorithms",
          blockKind: "heading",
          topicId: "t2",
          citations: [],
        },
        {
          index: 2,
          title: "Exotic Replacement Policies",
          content: "Exotic Replacement Policies",
          blockKind: "heading",
          topicId: "t3",
          citations: [],
        },
      ],
    };

    const html = renderToStaticMarkup(
      <MemoryRouter>
        <EnrichedView note={mockNote} onCitation={vi.fn()} initialSnapshot={snapshot} />
      </MemoryRouter>,
    );

    // Note-level summary
    expect(html).toContain("2 of 3 topics have reference material.");

    // Coverage badges
    expect(html).toContain("Reference found");
    expect(html).toContain("Limited reference");
    expect(html).toContain("No reference found");

    // Guidance link for topic with 'none'
    expect(html).toContain("No reference book covers this topic yet. Your notes are kept as written.");
    expect(html).toContain("Add a reference book for Computer Science");
    expect(html).toContain('href="/subjects/sub-cs-1/references"');
  });

  it("renders honest addition labels for supported and partial additions (PR 3 §3.2)", () => {
    const snapshot: EnrichmentSnapshot = {
      state: "enriched",
      generatedAt: "2026-10-30T10:00:00Z",
      blocks: [
        {
          index: 0,
          title: "",
          content: "Supported addition derived from textbook passage.",
          blockKind: "addition",
          supportStatus: "supported",
          citations: [],
        },
        {
          index: 1,
          title: "",
          content: "Partial addition extending beyond the cited reference.",
          blockKind: "addition",
          supportStatus: "partial",
          citations: [],
        },
      ],
    };

    const html = renderToStaticMarkup(
      <MemoryRouter>
        <EnrichedView note={mockNote} onCitation={vi.fn()} initialSnapshot={snapshot} />
      </MemoryRouter>,
    );

    // Supported label
    expect(html).toContain("From your reference");
    expect(html).toContain("border-left:4px solid #4f5bd5");

    // Partial label and lighter border
    expect(html).toContain("Extends the reference");
    expect(html).toContain("border-left:4px solid #93c5fd");
    expect(html).toContain("This goes beyond the cited passage. Check it against your textbook.");
  });

  it("renders reference library changed banner when referenceLibraryChanged is true (PR 3 §3.3)", () => {
    const snapshot: EnrichmentSnapshot = {
      state: "enriched",
      generatedAt: "2026-10-30T10:00:00Z",
      referenceLibraryChanged: true,
      blocks: [],
    };

    const html = renderToStaticMarkup(
      <MemoryRouter>
        <EnrichedView note={mockNote} onCitation={vi.fn()} initialSnapshot={snapshot} />
      </MemoryRouter>,
    );

    expect(html).toContain("Your reference library changed since this note was enriched.");
    expect(html).toContain("Regenerate");
  });

  it("renders progress with estimate and stage description during run (PR 3 §3.4)", () => {
    const snapshot: EnrichmentSnapshot = {
      state: "enriching",
      blocks: [],
      generatedAt: null,
      latestJob: {
        id: "job-1",
        status: "running",
        progress: {
          stages_completed: ["classify", "plan"],
          current_stage: "research 2 of 3",
          topics_completed: 1,
          topics_total: 3,
        },
      },
    };

    const html = renderToStaticMarkup(
      <MemoryRouter>
        <EnrichedView note={mockNote} onCitation={vi.fn()} initialSnapshot={snapshot} />
      </MemoryRouter>,
    );

    expect(html).toContain("Enriching your notes, this takes up to 2–3 minutes.");
    expect(html).toContain("Current step: Researching references (2 of 3)...");
    expect(html).toContain("Topics completed: 1 / 3");
  });
});
