import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { Breadcrumbs } from "../layout/Breadcrumbs";
import { ModuleProvider, useSubjectModule } from "../modules/ModuleContext";
import { ErrorState, SkeletonRows } from "../ui/primitives";
import { ClipboardIcon, PlusIcon } from "../ui/icons";
import { testsApi } from "../../services/api/tests";
import { useWorkspaceStore } from "../../state/workspaceStore";
import type { TestAttemptQuestion, TestSummary } from "../../types/domain";

/** Subject Tests (§23) — rendered only while TestsService is enabled. */
export function TestsPage() {
  const { subjectId } = useParams<{ subjectId: string }>();
  const subjects = useWorkspaceStore((s) => s.subjects);
  const subjectName = subjects.find((s) => s.id === subjectId)?.name ?? "";
  const { moduleId, services } = useSubjectModule(subjectId);

  const [tests, setTests] = useState<TestSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [activeTest, setActiveTest] = useState<TestSummary | null>(null);
  const { t } = useTranslation();

  async function load() {
    setError(null);
    try {
      setTests(await testsApi.list());
    } catch {
      setError(t("tests.loadFailed"));
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const subjectTests = useMemo(
    () => (tests ?? []).filter((t) => !t.subjectId || t.subjectId === subjectId),
    [tests, subjectId],
  );

  async function createTest() {
    if (!subjectId) return;
    setCreating(true);
    setError(null);
    try {
      const created = await testsApi.create(
        subjectId,
        t("tests.defaultTitle", { subject: subjectName }),
      );
      setTests((prev) => [...(prev ?? []), created]);
    } catch {
      setError(t("tests.createFailed"));
    } finally {
      setCreating(false);
    }
  }

  return (
    <ModuleProvider value={{ moduleId, services }}>
      <div className="content__inner">
        <Breadcrumbs
          crumbs={[
            { label: "Subjects", to: "/subjects" },
            ...(subjectName ? [{ label: subjectName, to: `/subjects/${subjectId}` }] : []),
            { label: "Tests" },
          ]}
        />

        <div className="page-heading page-heading__row" style={{ marginTop: 14 }}>
          <div>
            <h1>{t("tests.title")}</h1>
            <p className="subtitle" style={{ marginTop: 5 }}>
              {t("tests.subtitle", { subject: subjectName })}
            </p>
          </div>
          <div className="page-heading__actions">
            <button type="button" className="btn btn--primary" onClick={() => void createTest()} disabled={creating}>
              <PlusIcon size={14} />
              {creating ? t("tests.creating") : t("tests.newTest")}
            </button>
          </div>
        </div>

        {error && (
          <div className="form-error" role="alert" style={{ marginBottom: 14 }}>
            {error}
          </div>
        )}

        {!tests && !error && <SkeletonRows count={4} />}

        {activeTest ? (
          <TestRunner test={activeTest} onExit={() => setActiveTest(null)} />
        ) : tests && subjectTests.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state__icon">
              <ClipboardIcon size={20} />
            </div>
            <div className="empty-state__title">{t("tests.emptyTitle")}</div>
            <div className="empty-state__desc">
              {t("tests.emptyDescription")}
            </div>
            <div className="empty-state__action">
              <button type="button" className="btn btn--primary" onClick={() => void createTest()}>
                <PlusIcon size={14} />
                {t("tests.newTest")}
              </button>
            </div>
          </div>
        ) : tests ? (
          <div className="stack">
            {subjectTests.map((test) => (
              <div key={test.id} className="card row" style={{ padding: "14px 18px", justifyContent: "space-between" }}>
                <div>
                  <div style={{ fontWeight: 600 }}>{test.title}</div>
                  <div className="faint small" style={{ marginTop: 2 }}>
                    {test.questionCount > 0
                      ? t("tests.questionCount", { count: test.questionCount })
                      : t("tests.questionsPending")}{" · "}
                    {test.status === "completed"
                      ? typeof test.mastery === "number"
                        ? `${t("tests.completed")} · ${t("tests.masterySuffix", { percent: Math.round(test.mastery * 100) })}`
                        : t("tests.completed")
                      : t("tests.ready")}
                  </div>
                </div>
                <button type="button" className="btn btn--secondary btn--sm" onClick={() => setActiveTest(test)}>
                  {test.status === "completed" ? t("tests.review") : t("tests.start")}
                </button>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </ModuleProvider>
  );
}

function TestRunner({ test, onExit }: { test: TestSummary; onExit: () => void }) {
  const { t } = useTranslation();
  const [questions, setQuestions] = useState<TestAttemptQuestion[] | null>(null);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [submitted, setSubmitted] = useState(false);
  const [score, setScore] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    testsApi
      .getQuestions(test.id)
      .then((qs) => !cancelled && setQuestions(qs))
      .catch(() => !cancelled && setError(t("tests.runner.loadFailedTitle")));
    return () => {
      cancelled = true;
    };
  }, [test.id]);

  async function submit() {
    try {
      const result = await testsApi.submitAttempt(test.id, answers);
      setScore(result.score);
      setSubmitted(true);
    } catch {
      // Grade locally when attempts aren't supported yet.
      const correct = (questions ?? []).filter(
        (q) => q.answerIndex != null && answers[q.id] === q.answerIndex,
      ).length;
      setScore(questions?.length ? correct / questions.length : 0);
      setSubmitted(true);
    }
  }

  if (error) {
    return (
      <ErrorState
        title={t("tests.runner.loadFailedTitle")}
        message={t("errors.genericTryAgain")}
        onRetry={onExit}
        retryLabel={t("tests.runner.retryBackLabel")}
      />
    );
  }
  if (!questions) {
    return <SkeletonRows count={3} />;
  }
  if (questions.length === 0) {
    return (
      <ErrorState
        title={t("tests.runner.noQuestionsTitle")}
        message={t("tests.runner.noQuestionsMessage")}
        onRetry={onExit}
        retryLabel={t("tests.runner.retryBackLabel")}
      />
    );
  }

  const answeredCount = Object.keys(answers).length;
  const correctCount = questions.filter(
    (q) => q.answerIndex != null && answers[q.id] === q.answerIndex,
  ).length;
  const localScore = questions.length ? correctCount / questions.length : 0;

  return (
    <div>
      <div className="row" style={{ marginBottom: 18 }}>
        <button type="button" className="btn btn--ghost btn--sm" onClick={onExit}>
          ‹ {t("tests.runner.allTests")}
        </button>
        <span className="faint small">
          {t("tests.runner.answered", { answered: answeredCount, total: questions.length })}
        </span>
        <span style={{ flex: 1 }} />
        {!submitted ? (
          <button type="submit" className="btn btn--primary btn--sm" form="test-runner-form" disabled={answeredCount === 0}>
            {t("tests.runner.submit")}
          </button>
        ) : (
          <span className="chip chip--green">
            {t("tests.runner.score", { value: Math.round((score ?? localScore) * 100) })}
          </span>
        )}
      </div>

      <form
        id="test-runner-form"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        {questions.map((q, qi) => (
          <fieldset key={q.id} className="test-runner-question" style={{ border: "none", margin: 0, padding: 0 }}>
            <legend className="test-runner-question__prompt" style={{ padding: 0 }}>
              {qi + 1}. {q.prompt}
            </legend>
            {q.options.map((option, oi) => {
              const chosen = answers[q.id] === oi;
              const isAnswer = submitted && q.answerIndex === oi;
              const isWrongChoice = submitted && chosen && q.answerIndex !== oi;
              return (
                <label
                  key={oi}
                  className={[
                    "option-row",
                    chosen && !submitted ? "selected" : "",
                    isAnswer ? "correct" : "",
                    isWrongChoice ? "incorrect" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                >
                  <input
                    type="radio"
                    name={q.id}
                    className="visually-hidden"
                    disabled={submitted}
                    checked={chosen}
                    onChange={() => setAnswers((prev) => ({ ...prev, [q.id]: oi }))}
                  />
                  <span className="option-key">{String.fromCharCode(65 + oi)}</span>
                  <span>{option}</span>
                </label>
              );
            })}
            {submitted && q.answerIndex == null && (
              <p className="hint-text">{t("tests.runner.correctAnswerMissing")}</p>
            )}
          </fieldset>
        ))}
      </form>

      {submitted && (
        <div style={{ marginTop: 10 }}>
          <div className="mastery-bar" aria-label={t("tests.masterySuffix", { percent: Math.round((score ?? localScore) * 100) })}>
            <div className="mastery-bar__fill" style={{ width: `${Math.round((score ?? localScore) * 100)}%` }} />
          </div>
          <p className="hint-text" style={{ marginTop: 6 }}>
            {t("tests.runner.masteryHint")}
          </p>
        </div>
      )}
    </div>
  );
}
