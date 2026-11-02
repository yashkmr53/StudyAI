import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
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
    documentId: "doc-123",
    title: "Operating Systems Memory Management",
    source: "upload",
    sourceType: "pdf",
    folderId: "f-1",
    tags: [],
    pageCount: 1,
    reviewStatus: "approved",
    isApproved: true,
    hasEnrichment: true,
    isProcessing: false,
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
      <EnrichedView note={mockNote} onCitation={vi.fn()} initialSnapshot={snapshot} />,
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
      <EnrichedView note={mockNote} onCitation={vi.fn()} initialSnapshot={snapshot} />,
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
      <EnrichedView note={mockNote} onCitation={vi.fn()} initialSnapshot={snapshot} />,
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
      <EnrichedView note={mockNote} onCitation={vi.fn()} initialSnapshot={snapshot} />,
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
});
