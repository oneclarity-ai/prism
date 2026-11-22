import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { STATE_TEXT, STATUS_TEXT, STATUS_TONE, SEVERITY_TONE, isLink, minutesText, money } from "./helpers";
import { Btn, Fact, QaChip, metaString, useRun } from "./parts";
import { downloadFile, getState, screenUrl } from "./store";
import { isWorkReport, type ChatMessageLike, type QaReport, type WorkReport } from "./types";

function Lightbox({ runId, index, label, onClose }: { runId: string; index: number; label?: string; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [src, setSrc] = useState<string | undefined>();
  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);
  useEffect(() => {
    let current = true;
    screenUrl(runId, index)
      .then((url) => {
        if (current) setSrc(url);
      })
      .catch(() => {});
    return () => {
      current = false;
    };
  }, [runId, index]);
  return createPortal(
    <dialog
      ref={ref}
      className="qa-lightbox"
      onClose={onClose}
      onClick={(event) => {
        if (event.target === event.currentTarget) event.currentTarget.close();
      }}
    >
      <img alt={label || "Screenshot"} src={src} />
      <Btn label="Close" className="button secondary" onClick={() => ref.current?.close()} />
    </dialog>,
    document.body,
  );
}

function Thumb({ runId, index, label }: { runId: string; index: number; label?: string }) {
  const [url, setUrl] = useState<string | undefined>(() => getState().screens.get(`${runId}:${index}`));
  const [failed, setFailed] = useState(false);
  const [zoomed, setZoomed] = useState(false);
  useEffect(() => {
    let current = true;
    screenUrl(runId, index)
      .then((value) => {
        if (current) setUrl(value);
      })
      .catch(() => {
        if (current) setFailed(true);
      });
    return () => {
      current = false;
    };
  }, [runId, index]);
  if (failed) return null;
  return (
    <>
      <img className="qa-thumb" alt={label || "Screenshot"} loading="lazy" src={url} onClick={() => setZoomed(true)} />
      {zoomed ? <Lightbox runId={runId} index={index} label={label} onClose={() => setZoomed(false)} /> : null}
    </>
  );
}

function Thumbs({ runId, screens, limit, label }: { runId: string; screens: number[]; limit: number; label: string }) {
  return (
    <div className="qa-thumbs">
      {screens.slice(0, limit).map((n) => (
        <Thumb key={n} runId={runId} index={n} label={label} />
      ))}
    </div>
  );
}

function Cell({ value }: { value: unknown }) {
  const text = String(value ?? "");
  if (!isLink(text)) return <>{text}</>;
  return (
    <a href={text} target="_blank" rel="noopener noreferrer">
      {text.replace(/^https?:\/\//i, "")}
    </a>
  );
}

function BulletSection({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="qa-section">
      <h4>{title}</h4>
      <ul className="qa-criteria">
        {items.map((item, index) => (
          <li key={index}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function WorkReportView({ runId, report }: { runId: string; report: WorkReport }) {
  const columns = report.columns ?? [];
  const foot = [minutesText(report.duration_seconds), money(report.cost_usd)].filter(Boolean).join(" · ");
  return (
    <div className="qa-report">
      <div className="qa-counts">
        {report.outcome !== "succeeded" ? <QaChip tone="orange">{STATE_TEXT[report.outcome ?? ""] || report.outcome}</QaChip> : null}
        {report.row_count ? <QaChip tone="green">{`${report.row_count} found`}</QaChip> : null}
        {(report.files || []).map((file, index) => (
          <Btn key={index} label={`Download ${file.name}`} className="mini-button file-chip" onClick={() => void downloadFile(runId, file)} />
        ))}
      </div>
      {report.rows?.length ? (
        <div className="qa-table-wrap" tabIndex={0} role="region" aria-label="Results">
          <table className="qa-table">
            <thead>
              <tr>
                {columns.map((column, index) => (
                  <th key={index}>{column.replace(/[_-]+/g, " ")}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {report.rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {columns.map((column, index) => (
                    <td key={index}>
                      <Cell value={row[column]} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {report.needs_attention?.length ? <BulletSection title="Needs your attention" items={report.needs_attention} /> : null}
      {report.next_steps?.length ? <BulletSection title="What I can do next" items={report.next_steps} /> : null}
      <p className="qa-muted qa-foot">{foot}</p>
    </div>
  );
}

function QaReportView({ runId, report }: { runId: string; report: QaReport }) {
  const counts = report.counts || {};
  const bugs = report.bugs || [];
  const cases = report.cases || [];
  const pages = report.pages || [];
  const foot = [minutesText(report.duration_seconds), `${pages.length} page${pages.length === 1 ? "" : "s"}`, money(report.cost_usd)].filter(Boolean).join(" · ");
  return (
    <div className="qa-report">
      <div className="qa-counts">
        <QaChip tone="green">{`${counts.pass || 0} passed`}</QaChip>
        {counts.fail ? <QaChip tone="red">{`${counts.fail} failed`}</QaChip> : null}
        {counts.blocked ? <QaChip tone="orange">{`${counts.blocked} couldn't check`}</QaChip> : null}
        {counts.skipped ? <QaChip tone="gray">{`${counts.skipped} skipped`}</QaChip> : null}
        {bugs.length ? <QaChip tone="red">{`${bugs.length} issue${bugs.length === 1 ? "" : "s"}`}</QaChip> : null}
      </div>
      {report.coverage ? (
        <>
          {report.partial ? <p className="qa-muted">Partial coverage: some discovered pages remain untested.</p> : null}
          <details className="qa-cases">
            <summary>{`Page coverage (${report.coverage.pages?.length || 0})`}</summary>
            {(report.coverage.pages || []).map((page, index) => (
              <div className="qa-case" key={index}>
                <strong>{`${page.status === "tested" ? "Tested" : "Untested"}: ${page.url}`}</strong>
                {page.reason || page.status !== "tested" ? <p className="qa-muted">{page.reason || "Not tested before this session ended."}</p> : null}
              </div>
            ))}
            {report.coverage.truncated ? <p className="qa-muted">The discovery list reached its safety limit. More routes may exist.</p> : null}
          </details>
        </>
      ) : null}
      {bugs.length ? (
        <div className="qa-section">
          <h4>Issues</h4>
          {bugs.map((bug, index) => (
            <div className="qa-card" key={index}>
              <div className="qa-card-head">
                <strong>{bug.title}</strong>
                <QaChip tone={SEVERITY_TONE[bug.severity] || "gray"}>{bug.severity}</QaChip>
              </div>
              {bug.steps ? <Fact label="Steps" value={bug.steps} /> : null}
              {bug.expected ? <Fact label="Expected" value={bug.expected} /> : null}
              {bug.actual ? <Fact label="Actually" value={bug.actual} /> : null}
              {bug.screens?.length ? <Thumbs runId={runId} screens={bug.screens} limit={3} label={bug.title} /> : null}
            </div>
          ))}
        </div>
      ) : null}
      {cases.length ? (
        <details className="qa-cases" open={cases.length <= 8}>
          <summary>{`All checks (${cases.length})`}</summary>
          {cases.map((item, index) => {
            const steps = [item.given && `Given ${item.given}`, item.when && `when ${item.when}`, item.then && `then ${item.then}`].filter(Boolean).join(", ");
            return (
              <div className="qa-case" key={index}>
                <div className="qa-case-head">
                  <QaChip tone={STATUS_TONE[item.status] || "gray"}>{STATUS_TEXT[item.status] || item.status}</QaChip>
                  <strong>{item.title}</strong>
                </div>
                {steps ? <p className="qa-muted">{steps}</p> : null}
                {item.notes ? <p className="qa-notes">{item.notes}</p> : null}
                {item.screens?.length ? <Thumbs runId={runId} screens={item.screens} limit={2} label={item.title} /> : null}
              </div>
            );
          })}
        </details>
      ) : null}
      <p className="qa-muted qa-foot">{foot}</p>
    </div>
  );
}

/** `qa_report` / `work_report` message card. */
export function ReportCard({ message }: { message: ChatMessageLike }) {
  const runId = metaString(message, "qa_run_id");
  const run = useRun(runId);
  const report = run?.report;
  if (!runId || !report) return <div className="qa-report" />;
  return isWorkReport(report) ? <WorkReportView runId={runId} report={report} /> : <QaReportView runId={runId} report={report} />;
}
