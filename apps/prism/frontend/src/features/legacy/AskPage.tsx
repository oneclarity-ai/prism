import { useState, type FormEvent } from "react";
import { agentApi, errorMessage, jsonBody } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import type { Schema } from "@/types";
import { humanize } from "./format";

const SUGGESTIONS = [
  "Who is blocked right now?",
  "What needs my attention?",
  "What changed today?",
  "Which commitments are at risk?",
];

export function AskPage() {
  const { setStatus } = useApp();
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [answer, setAnswer] = useState<Schema<"ManagementQueryAnswer"> | null>(null);

  const ask = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    setBusy(true);
    try {
      setAnswer(await agentApi<Schema<"ManagementQueryAnswer">>("/api/v2/management/query", { method: "POST", ...jsonBody({ question: trimmed }) }));
    } catch (error) {
      setStatus(errorMessage(error), true);
    } finally {
      setBusy(false);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void ask(question);
  };

  return (
    <section className="panel management-query-panel">
      <div className="panel-heading">
        <div>
          <h2>Ask about the team</h2>
          <p className="panel-note">Answers come from structured organisational state and include evidence.</p>
        </div>
      </div>
      <form id="management-query-form" className="management-query-form" onSubmit={submit}>
        <label htmlFor="management-query-input">Question</label>
        <div className="management-query-row">
          <input
            id="management-query-input"
            maxLength={1000}
            placeholder="For example: Who is blocked, and what needs my attention?"
            required
            value={question}
            onChange={(event) => setQuestion(event.currentTarget.value)}
          />
          <button className="button" type="submit" disabled={busy}>
            Ask
          </button>
        </div>
        <div className="query-suggestions" aria-label="Suggested questions">
          {SUGGESTIONS.map((suggestion) => (
            <button
              key={suggestion}
              className="mini-button"
              type="button"
              data-query={suggestion}
              onClick={() => {
                setQuestion(suggestion);
                void ask(suggestion);
              }}
            >
              {suggestion}
            </button>
          ))}
        </div>
      </form>
      <div id="management-query-results" className="management-query-results" hidden={!answer}>
        {answer ? (
          <>
            <span className="answer-type">{humanize(answer.answer_type)}</span>
            <p>{answer.answer}</p>
            {answer.uncertainty ? <p className="query-uncertainty">{answer.uncertainty}</p> : null}
            {answer.evidence?.length ? (
              <details>
                <summary>Evidence ({answer.evidence.length})</summary>
                <ul>
                  {answer.evidence.map((value, index) => (
                    <li key={index}>{value}</li>
                  ))}
                </ul>
              </details>
            ) : null}
          </>
        ) : null}
      </div>
    </section>
  );
}
