import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { Breadcrumbs } from "../layout/Breadcrumbs";
import { ModuleProvider, useSubjectModule } from "../modules/ModuleContext";
import { EmptyState, ErrorState, SkeletonRows } from "../ui/primitives";
import { QuizIcon } from "../ui/icons";
import { questionsApi } from "../../services/api/questions";
import { useWorkspaceStore } from "../../state/workspaceStore";
import type { PracticeQuestion } from "../../types/domain";

/** Practice QA (§24) — subject-scoped; only when QAService is enabled. */
export function PracticePage() {
  const { subjectId } = useParams<{ subjectId: string }>();
  const subjects = useWorkspaceStore((s) => s.subjects);
  const notes = useWorkspaceStore((s) => s.notes);
  const subjectName = subjects.find((s) => s.id === subjectId)?.name ?? "";
  const { moduleId, services } = useSubjectModule(subjectId);
  const { t } = useTranslation();

  const [questions, setQuestions] = useState<PracticeQuestion[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      // Aggregate per-document question sets across the subject's notes.
      const noteIds = notes
        .filter((n) => n.subjectId === subjectId && n.source === "upload")
        .map((n) => n.refId);
      const batches = await Promise.allSettled(noteIds.map((id) => questionsApi.listForDocument(id)));
      const merged = batches.flatMap((b) => (b.status === "fulfilled" ? b.value : []));
      setQuestions(merged);
    } catch {
      setError(t("practice.loadFailed"));
    }
  }, [notes, subjectId]);

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <ModuleProvider value={{ moduleId, services }}>
      <div className="content__inner" style={{ maxWidth: 760 }}>
        <Breadcrumbs
          crumbs={[
            { label: t("common.breadcrumb.subjects"), to: "/subjects" },
            ...(subjectName ? [{ label: subjectName, to: `/subjects/${subjectId}` }] : []),
            { label: t("practice.title") },
          ]}
        />

        <div className="page-heading" style={{ marginTop: 14 }}>
          <h1>{t("practice.title")}</h1>
          <p className="subtitle" style={{ marginTop: 5 }}>
            {t("practice.subtitle", { subject: subjectName })}
          </p>
        </div>

        {error && <ErrorState message={error} onRetry={() => void load()} />}

        {!questions && !error && <SkeletonRows count={4} />}

        {questions && questions.length === 0 && (
          <EmptyState
            icon={<QuizIcon size={20} />}
            title={t("practice.emptyTitle")}
            description={t("practice.emptyDescription")}
          />
        )}

        {questions && questions.length > 0 && (
          <QuestionRunner questions={questions.filter((q) => !q.stale)} />
        )}
      </div>
    </ModuleProvider>
  );
}

function QuestionRunner({ questions }: { questions: PracticeQuestion[] }) {
  const { t } = useTranslation();
  const [index, setIndex] = useState(0);
  const [chosen, setChosen] = useState<number | null>(null);
  const [correctCount, setCorrectCount] = useState(0);
  const [done, setDone] = useState(false);

  if (questions.length === 0) {
    return (
      <EmptyState
        icon={<QuizIcon size={20} />}
        title={t("practice.allCaughtUpTitle")}
        description={t("practice.allCaughtUpDescription")}
      />
    );
  }

  const question = questions[Math.min(index, questions.length - 1)];

  function answer(optionIndex: number) {
    if (chosen !== null) return;
    setChosen(optionIndex);
    if (optionIndex === question.answerIndex) {
      setCorrectCount((c) => c + 1);
    }
  }

  function next() {
    if (index + 1 >= questions.length) {
      setDone(true);
      return;
    }
    setIndex((i) => i + 1);
    setChosen(null);
  }

  if (done) {
    return (
      <div className="card" style={{ padding: 28, textAlign: "center" }}>
        <h2 style={{ fontSize: 18 }}>{t("practice.sessionCompleteTitle")}</h2>
        <p className="muted" style={{ marginTop: 8 }}>
          {t("practice.sessionSummary", { correct: correctCount, total: questions.length })}
        </p>
        <div className="mastery-bar" style={{ marginTop: 16 }} aria-label={t("practice.sessionAccuracyAria")}>
          <div
            className="mastery-bar__fill"
            style={{ width: `${Math.round((correctCount / questions.length) * 100)}%` }}
          />
        </div>
        <button
          type="button"
          className="btn btn--secondary"
          style={{ marginTop: 18 }}
          onClick={() => {
            setIndex(0);
            setCorrectCount(0);
            setDone(false);
            setChosen(null);
          }}
        >
          {t("practice.practiceAgain")}
        </button>
      </div>
    );
  }

  return (
    <div className="card" style={{ padding: 26 }}>
      <div className="row" style={{ marginBottom: 14 }}>
        <span className="chip chip--gray">
          {t("practice.questionOf", { index: index + 1, total: questions.length })}
        </span>
        <span className="chip chip--gray">
          <span className={`difficulty-dot difficulty-${question.difficulty}`} aria-hidden />
          {t(`common.difficulty.${question.difficulty}`)}
        </span>
        <span style={{ flex: 1 }} />
        <span className="faint small">
          {t("practice.correctSoFar", { count: correctCount })}
        </span>
      </div>

      <p className="test-runner-question__prompt">{question.prompt}</p>

      <div role="radiogroup" aria-label={t("practice.answersAria")}>
        {question.options.map((option, oi) => {
          const isAnswer = chosen !== null && oi === question.answerIndex;
          const isWrongPick = chosen === oi && oi !== question.answerIndex;
          return (
            <button
              key={oi}
              type="button"
              disabled={chosen !== null}
              className={[
                "option-row",
                isAnswer ? "correct" : "",
                isWrongPick ? "incorrect" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              onClick={() => answer(oi)}
            >
              <span className="option-key">{String.fromCharCode(65 + oi)}</span>
              <span>{option}</span>
            </button>
          );
        })}
      </div>

      {chosen !== null && (
        <div className="row" style={{ marginTop: 14 }}>
          {chosen === question.answerIndex ? (
            <span className="chip chip--green">{t("practice.correct")}</span>
          ) : (
            <span className="chip chip--red">{t("practice.notQuite")}</span>
          )}
          <span style={{ flex: 1 }} />
          <button type="button" className="btn btn--primary btn--sm" onClick={next}>
            {index + 1 >= questions.length ? t("common.actions.finish") : t("practice.nextQuestion")}
          </button>
        </div>
      )}
    </div>
  );
}
