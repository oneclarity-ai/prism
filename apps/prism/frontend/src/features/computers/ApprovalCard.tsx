import { useEffect, useState } from "react";
import { SEVERITY_TONE, isActive, money, stripScheme } from "./helpers";
import { Btn, Fact, QaChip, metaString, onSubmit, EditField, useRun } from "./parts";
import { cancelRun, decideApproval, frameUrl, getState, watchRun } from "./store";
import type { ApprovalDecision, ChatMessageLike, QaApproval, QaRun } from "./types";

/** Disables the card's buttons while a decision is on its way; re-enables them when it failed. */
function useDecide(approval: QaApproval) {
  const [busy, setBusy] = useState(false);
  const decide = async (body: ApprovalDecision): Promise<void> => {
    setBusy(true);
    try {
      await decideApproval(approval, body);
    } finally {
      setBusy(false);
    }
  };
  return { busy, decide };
}

const decidedLine = (approval: QaApproval, yes: string, no: string) => <p className="qa-muted">{approval.status === "approved" ? yes : no}</p>;

function ApprovalFrame({ run }: { run: QaRun }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let current = true;
    frameUrl(run)
      .then((value) => {
        if (current) setUrl(value);
      })
      .catch(() => {
        if (current) setFailed(true);
      });
    return () => {
      current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload only when the frame changes, not on every run update
  }, [run.id, run.frame]);
  if (failed) return null;
  return <img className="qa-thumb wide" alt="What the screen shows right now" src={url ?? undefined} />;
}

function OutwardCard({ run, approval }: { run: QaRun; approval: QaApproval }) {
  const { busy, decide } = useDecide(approval);
  const view = approval.view || {};
  return (
    <div className="qa-plan">
      <div className="qa-card">
        <div className="qa-card-head">
          <strong>Before I go ahead</strong>
        </div>
        {view.summary ? <Fact label="I'm about to" value={view.summary} /> : null}
        {view.site ? <Fact label="Where" value={view.site} /> : null}
        {view.details ? <Fact label="Details" value={view.details} /> : null}
        {view.frame && approval.status === "pending" ? <ApprovalFrame run={run} /> : null}
      </div>
      {approval.status === "pending" ? (
        <div className="qa-actions">
          <Btn label="Allow" className="button" disabled={busy} onClick={() => void decide({ decision: "approve" })} />
          <Btn label="Don't" className="button secondary" disabled={busy} onClick={() => void decide({ decision: "reject" })} />
        </div>
      ) : (
        decidedLine(approval, "You allowed it.", "You said no, so I didn't do it.")
      )}
    </div>
  );
}

function QuestionCard({ approval }: { approval: QaApproval }) {
  const { busy, decide } = useDecide(approval);
  const [answer, setAnswer] = useState("");
  if (approval.status !== "pending") return <div className="qa-plan">{decidedLine(approval, "You answered.", "You skipped this question.")}</div>;
  return (
    <div className="qa-plan">
      <form
        className="qa-edit"
        onSubmit={onSubmit(() => {
          if (answer.trim()) void decide({ decision: "approve", answer });
        })}
      >
        <textarea rows={2} maxLength={1000} required aria-label="Your answer" value={answer} onChange={(event) => setAnswer(event.target.value)} />
        <div className="qa-actions">
          <Btn label="Send answer" className="button" type="submit" disabled={busy} />
          <Btn label="Skip" className="button secondary" disabled={busy} onClick={() => void decide({ decision: "reject" })} />
        </div>
      </form>
    </div>
  );
}

function LoginCard({ approval }: { approval: QaApproval }) {
  const { busy, decide } = useDecide(approval);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [keep, setKeep] = useState("true");
  const name = getState().prism?.name || "Prism";
  const site = approval.view?.site || "this site";
  const shortSite = stripScheme(site);
  const submit = async () => {
    const login = { username, password, remember: keep === "true" };
    setPassword(""); // the password leaves the page as soon as it is sent
    await decide({ decision: "approve", login });
    login.password = "";
  };
  return (
    <div className="qa-plan">
      <div className="qa-card">
        <div className="qa-card-head">
          <strong>{`${name} needs to sign in to ${shortSite}`}</strong>
        </div>
        {approval.view?.reason ? <p className="qa-muted">{approval.view.reason}</p> : null}
      </div>
      {approval.status !== "pending" ? (
        decidedLine(approval, "You gave a login.", "You skipped signing in.")
      ) : (
        <form className="qa-edit qa-login" autoComplete="off" onSubmit={onSubmit(() => void submit())}>
          <EditField label="Username or email">
            <input type="text" name="prism-site-username" autoComplete="off" required maxLength={200} value={username} onChange={(event) => setUsername(event.target.value)} />
          </EditField>
          <EditField label="Password">
            <input type="password" name="prism-site-password" autoComplete="new-password" required maxLength={500} value={password} onChange={(event) => setPassword(event.target.value)} />
          </EditField>
          <EditField label="Keep it">
            <select aria-label="How long to keep it" value={keep} onChange={(event) => setKeep(event.target.value)}>
              <option value="true">{`Remember for ${name}`}</option>
              <option value="false">Use once, then forget</option>
            </select>
          </EditField>
          <p className="qa-muted">{`Only ${name}'s computer uses this. It is encrypted, never shown in chat, and never seen by the AI model.`}</p>
          <div className="qa-actions">
            <Btn label="Sign in" className="button" type="submit" disabled={busy} />
            <Btn label={`Skip ${shortSite}`} className="button secondary" disabled={busy} onClick={() => void decide({ decision: "reject" })} />
          </div>
        </form>
      )}
    </div>
  );
}

function BudgetCard({ approval }: { approval: QaApproval }) {
  const { busy, decide } = useDecide(approval);
  const view = approval.view || {};
  return (
    <div className="qa-plan">
      <div className="qa-card">
        <strong>More pages remain to test</strong>
        <p className="qa-muted">{view.reason || "The current testing limits are almost used."}</p>
        <Fact label="New total limits" value={`${view.max_turns} steps · ${money(view.budget_usd)} total budget`} />
      </div>
      {approval.status === "pending" ? (
        <div className="qa-actions">
          <Btn label="Extend and continue" className="button" disabled={busy} onClick={() => void decide({ decision: "approve" })} />
          <Btn label="Finish with partial report" className="button secondary" disabled={busy} onClick={() => void decide({ decision: "reject" })} />
        </div>
      ) : (
        decidedLine(approval, "You extended the limits.", "You finished with a partial report.")
      )}
    </div>
  );
}

function BugCard({ approval }: { approval: QaApproval }) {
  const { busy, decide } = useDecide(approval);
  return (
    <div className="qa-plan">
      <div className="qa-card">
        <div className="qa-card-head">
          <strong>{approval.title || "A bug I found"}</strong>
          <QaChip tone={SEVERITY_TONE[approval.severity ?? ""] || "gray"}>{approval.severity || "medium"}</QaChip>
        </div>
        {approval.steps ? <Fact label="Steps" value={approval.steps} /> : null}
        {approval.expected ? <Fact label="Expected" value={approval.expected} /> : null}
        {approval.actual ? <Fact label="Actually" value={approval.actual} /> : null}
      </div>
      {approval.status === "pending" ? (
        <div className="qa-actions">
          <Btn label="File it" className="button" disabled={busy} onClick={() => void decide({ decision: "approve" })} />
          <Btn label="Don't file" className="button secondary" disabled={busy} onClick={() => void decide({ decision: "reject" })} />
        </div>
      ) : (
        <p className="qa-muted">{approval.status === "approved" ? "You approved filing this." : "You chose not to file this."}</p>
      )}
    </div>
  );
}

/** `qa_approval` / `work_approval` message card. */
export function ApprovalCard({ message }: { message: ChatMessageLike }) {
  const run = useRun(metaString(message, "qa_run_id"));
  const approvalId = metaString(message, "qa_approval_id");
  const approval = run?.approvals?.find((item) => item.id === approvalId);
  if (!run || !approval) return <div className="qa-plan" />;
  switch (approval.kind) {
    case "outward_action":
    case "site_access":
      return <OutwardCard run={run} approval={approval} />;
    case "budget_extension":
      return <BudgetCard approval={approval} />;
    case "question":
      return <QuestionCard approval={approval} />;
    case "login":
      return <LoginCard approval={approval} />;
    default:
      return <BugCard approval={approval} />;
  }
}

/** `work_busy` message card: Watch / Stop while the other task still runs. */
export function BusyCard({ message }: { message: ChatMessageLike }) {
  const run = useRun(metaString(message, "qa_run_id"));
  return (
    <div className="qa-plan">
      {run && isActive(run) ? (
        <div className="qa-actions">
          <Btn label="Watch" className="mini-button" onClick={() => watchRun(run)} />
          <Btn label="Stop that task" className="mini-button" onClick={() => void cancelRun(run)} />
        </div>
      ) : null}
    </div>
  );
}
