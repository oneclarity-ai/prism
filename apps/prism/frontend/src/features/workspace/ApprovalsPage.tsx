import { useEffect, useState } from "react";
import { agentApi, errorMessage, jsonBody } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { usePrisms } from "@/features/prisms/PrismsContext";
import { useOpenWorkPrism } from "./WorkPage";
import { loadApprovals, setApprovalStatus, syncPrismList, useUnifiedWork, type WorkApproval } from "./unified-work";

const DETAILS = [
  ["Severity", "severity"],
  ["Steps", "steps"],
  ["Expected", "expected"],
  ["Actual", "actual"],
  ["Details", "details"],
  ["Reason", "reason"],
] as const;
const DECISIONS = [
  ["Reject", "reject", "mini-button"],
  ["Approve", "approve", "mini-button primary"],
] as const;

function ApprovalCard({ item, onOpen }: { item: WorkApproval; onOpen: (prismId: string, runId: string) => void }) {
  const [deciding, setDeciding] = useState(false);
  const heading = item.kind === "bug_filing" ? item.payload.title || "File a bug" : item.payload.summary || item.payload.question || "Computer action needs review";
  const decide = async (decision: string) => {
    setDeciding(true);
    try {
      await agentApi(`/api/v2/qa/approvals/${item.id}/decision`, { method: "POST", ...jsonBody({ decision }) });
      await loadApprovals();
    } catch (error) {
      setApprovalStatus(errorMessage(error), true);
      setDeciding(false);
    }
  };
  return (
    <article className="unified-work-card approval-work-card">
      <h3>{heading}</h3>
      <p className="panel-note">{`${item.prism_name} · ${item.run_title} · ${String(item.kind).replaceAll("_", " ")}`}</p>
      {item.payload.site ? <p className="unified-work-detail">{`Site: ${item.payload.site}`}</p> : null}
      {DETAILS.map(([label, key]) =>
        item.payload[key] ? (
          <p className="unified-work-detail" key={key}>
            <strong>{`${label}: `}</strong>
            {String(item.payload[key])}
          </p>
        ) : null,
      )}
      <div className="unified-work-actions">
        <button type="button" className="mini-button" onClick={() => onOpen(item.prism_id, item.run_id)}>
          Open this work in Prism
        </button>
        {item.can_decide_here ? (
          DECISIONS.map(([label, decision, className]) => (
            <button key={decision} type="button" className={className} disabled={deciding} onClick={() => void decide(decision)}>
              {label}
            </button>
          ))
        ) : (
          <span className="panel-note">{item.kind === "login" ? "Sign-in decisions stay in the chat so credentials are handled safely." : "Answer this question in the Prism conversation."}</span>
        )}
      </div>
    </article>
  );
}

/** Inner content of `data-tab="approvals"`. */
export function ApprovalsPage() {
  const { activeTab } = useApp();
  const { prisms, loading } = usePrisms();
  const { approvals, approvalStatus } = useUnifiedWork();
  const openPrism = useOpenWorkPrism();

  useEffect(() => {
    if (activeTab === "approvals") void loadApprovals();
  }, [activeTab]);
  useEffect(() => {
    if (!loading) syncPrismList(prisms);
  }, [prisms, loading]);

  return (
    <>
      <div className="panel-heading">
        <div>
          <h2>Approval inbox</h2>
          <p className="panel-note">Review computer actions here. Questions and sign-ins continue in their Prism conversation.</p>
        </div>
        <button id="approval-refresh" className="mini-button" type="button" onClick={() => void loadApprovals()}>
          Refresh
        </button>
      </div>
      <p id="approval-status" className={`panel-note${approvalStatus.error ? " error" : ""}`} role="status" aria-live="polite">
        {approvalStatus.text}
      </p>
      <div id="work-approval-list" className="list empty-state">
        {approvals.kind === "initial" ? (
          "Loading approvals…"
        ) : approvals.kind === "loading" ? (
          <p className="panel-note">Loading approvals…</p>
        ) : approvals.kind === "error" ? (
          <p className="inline-error">{approvals.message}</p>
        ) : !approvals.items.length ? (
          <p className="empty-state">No computer actions are waiting for approval.</p>
        ) : (
          approvals.items.map((item) => <ApprovalCard key={item.id} item={item} onOpen={openPrism} />)
        )}
      </div>
    </>
  );
}
