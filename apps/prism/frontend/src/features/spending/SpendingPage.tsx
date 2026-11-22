import { CurrencyToggle } from "./CurrencyToggle";
import {
  COST_SOURCES,
  costStore,
  formatMoney,
  periodTotal,
  sumRows,
  useCostSnapshot,
  useCostSync,
  type AzureBilled,
  type CostData,
  type CostPeriod,
  type CostRange,
  type CostRow,
  type CostSnapshot,
  type CostSourceName,
  type CostView,
} from "./costStore";

const COST_LABELS: Record<string, string> = {
  qa_tester_test_runs: "QA tester: website test runs",
  qa_workspace_other_runs: "QA tester: runs started outside Prism",
  prism_computer_tasks: "Prism tasks on its own computer",
  prism_work_plan: "Task plans",
  prism_work_report: "Task reports",
  prism_work_intent: "Understanding task requests",
  prism_role_instructions: "Writing how a Prism works",
  prism_qa_plan: "QA tester: test plans",
  prism_qa_report: "QA tester: reports",
  prism_qa_followup: "QA tester: follow-up answers",
  prism_message_voice: "Wording drafted messages",
  prism_job_description: "Drafting job descriptions",
};

function label(name: unknown): string {
  const key = String(name);
  if (COST_LABELS[key]) return COST_LABELS[key];
  return String(name || "unknown")
    .replace(/[_-]+/g, " ")
    .replace(/^./, (c) => c.toUpperCase());
}

const number = (value: unknown): string => Number(value || 0).toLocaleString("en-IN");

function tokenLine(rows: readonly CostRow[]): string {
  const input = sumRows(rows, "input_tokens");
  const cached = sumRows(rows, "cached_input_tokens");
  const output = sumRows(rows, "output_tokens");
  return `${number(sumRows(rows, "calls"))} calls · ${number(input)} in (${number(cached)} cached) · ${number(output)} out`;
}

function billedLine(source: CostSourceName, billed: AzureBilled | null, currency: CostSnapshot["currency"], rate: number | null): string {
  if (!billed?.configured) return "";
  const row = billed.sources?.[source];
  if (!row) return "Azure billed: not set up for this source";
  if (row.error) return `Azure billed: ${row.error}`;
  const amount =
    row.currency === "USD"
      ? formatMoney(row.cost, currency, rate)
      : row.currency === "INR" && currency === "INR"
        ? `₹${Number(row.cost).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
        : `${Number(row.cost).toFixed(4)} ${row.currency || ""}`.trim();
  return `Azure billed: ${amount} (posts hours late)`;
}

const PERIODS: ReadonlyArray<readonly [string, CostPeriod]> = [
  ["Today", "today"],
  ["Last 7 days", "week"],
  ["This month", "month"],
  ["Total so far", "total"],
];

function providerName(provider: string): string {
  if (provider === "qa_workspace") return "Agentic swarm (upstream provider unrecorded)";
  if (provider === "azure_openai") return "Azure OpenAI";
  if (provider === "codex_local") return "Local Codex";
  if (provider === "openai") return "OpenAI";
  return label(provider);
}

function CostRows({ rows, total, view, money }: { rows: readonly CostRow[]; total: number; view: CostView; money: (value: unknown) => string }) {
  const used = rows.filter((row) => Number(row.estimated_cost_usd) > 0 || row.calls).sort((a, b) => Number(b.estimated_cost_usd) - Number(a.estimated_cost_usd));
  if (!used.length) {
    return (
      <div className="cost-list empty-state" data-cost-rows>
        No usage in this range.
      </div>
    );
  }
  return (
    <div className="cost-list" data-cost-rows>
      {used.map((row) => {
        const share = total > 0 ? Math.round((Number(row.estimated_cost_usd) / total) * 100) : 0;
        const unpriced = row.unpriced_calls ? ` · ${row.unpriced_calls} unpriced` : "";
        return (
          <div key={row.group} className="cost-row">
            <div className="cost-row-head">
              <span className="cost-name">{view === "model" ? String(row.group) : label(row.group)}</span>
              <strong>{money(row.estimated_cost_usd)}</strong>
            </div>
            <div className="cost-bar">
              <i style={{ width: `${Math.max(share, row.calls ? 2 : 0)}%` }} />
            </div>
            <span className="cost-meta">{`${tokenLine([row])} · ${share}%${unpriced}`}</span>
          </div>
        );
      })}
    </div>
  );
}

function costNote(data: CostData | null, failed: boolean): string {
  if (failed) return "Spend could not be loaded.";
  if (!data) return "Estimated from exact token counts and each model's rate.";
  const unpriced = COST_SOURCES.reduce((total, source) => total + sumRows(data.by_feature[source], "unpriced_calls"), 0);
  return (
    `Estimated from exact token counts and each model's rate, ${data.timezone} days.` +
    (unpriced ? ` ${unpriced} ${unpriced === 1 ? "call is" : "calls are"} missing a rate, so the real total may be higher.` : "")
  );
}

const RANGES: ReadonlyArray<readonly [CostRange, string]> = [
  ["today", "Today"],
  ["week", "7 days"],
  ["month", "This month"],
];
const VIEWS: ReadonlyArray<readonly [CostView, string]> = [
  ["feature", "By feature"],
  ["model", "By model"],
];
const SOURCE_TITLES: Record<CostSourceName, string> = { prism: "Prism", swarm: "Agentic swarm" };

export function SpendingPage() {
  useCostSync();
  const snap = useCostSnapshot();
  const { data, billed, currency, inrRate, range, view } = snap;
  const money = (value: unknown) => formatMoney(value, currency, inrRate);
  const dash = "—";
  const sourceTotal = (source: CostSourceName | "all", period: CostPeriod): string => {
    if (!data) return dash;
    return money(source === "all" ? periodTotal(data, period) : data.periods[period][source].estimated_cost_usd);
  };
  const providers = data ? [...(data.by_provider || [])].sort((a, b) => Number(b.estimated_cost_usd) - Number(a.estimated_cost_usd)) : null;

  return (
    <>
      <div className="spending-toolbar">
        <span id="cost-updated" className="cost-updated" aria-live="polite">
          {data && snap.stamp
            ? `${currency === "INR" && inrRate ? `1 USD = ₹${inrRate.toFixed(2)} · ` : ""}Updated ${snap.stamp.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`
            : ""}
        </span>
        <CurrencyToggle />
      </div>
      <div className="spend-grid" aria-label="Spend summary">
        {PERIODS.map(([title, period]) => (
          <article key={period} className="stat-card spend-card">
            <span className="spend-label">{title}</span>
            <strong className="spend-total" data-cost={`all:${period}`}>
              {sourceTotal("all", period)}
            </strong>
            <dl className="spend-split">
              <div>
                <dt>Prism</dt>
                <dd data-cost={`prism:${period}`}>{sourceTotal("prism", period)}</dd>
              </div>
              <div>
                <dt>Swarm</dt>
                <dd data-cost={`swarm:${period}`}>{sourceTotal("swarm", period)}</dd>
              </div>
            </dl>
          </article>
        ))}
      </div>
      <section className="panel spending-breakdown">
        <div className="panel-heading">
          <div>
            <h2>Breakdown</h2>
            <p id="cost-note" className="panel-note">
              {costNote(data, snap.failed)}
            </p>
          </div>
          <div className="cost-controls">
            <span className="currency-toggle" role="group" aria-label="Date range">
              {RANGES.map(([value, text]) => (
                <button key={value} type="button" data-cost-range={value} aria-pressed={range === value} onClick={() => costStore.setRange(value)}>
                  {text}
                </button>
              ))}
            </span>
            <span className="currency-toggle" role="group" aria-label="Breakdown">
              {VIEWS.map(([value, text]) => (
                <button key={value} type="button" data-cost-view={value} aria-pressed={view === value} onClick={() => costStore.setView(value)}>
                  {text}
                </button>
              ))}
            </span>
          </div>
        </div>
        <div className="settings-cost-summary">
          <span>Estimated total for this period</span>
          <strong id="settings-cost-total">{data ? money(periodTotal(data, range)) : dash}</strong>
          <small>Prism and swarm usage combined</small>
        </div>
        <div className="cost-split">
          {COST_SOURCES.map((source) => {
            const total = data ? sumRows(data.by_feature[source], "estimated_cost_usd") : 0;
            const azure = data ? billedLine(source, billed, currency, inrRate) : "";
            return (
              <section key={source} className="cost-source" data-cost-source={source}>
                <h3 className="subhead">{SOURCE_TITLES[source]}</h3>
                <p className="cost-big" data-cost-total>
                  {data ? money(total) : dash}
                </p>
                <p className="cost-meta" data-cost-tokens>
                  {data ? tokenLine(data.by_feature[source]) : ""}
                </p>
                <p className="cost-azure" data-cost-azure hidden={!azure}>
                  {azure}
                </p>
                <CostRows rows={data ? data[view === "model" ? "by_model" : "by_feature"][source] : []} total={total} view={view} money={money} />
              </section>
            );
          })}
        </div>
      </section>
      <section className="panel spending-providers">
        <div className="panel-heading">
          <div>
            <h2>By provider</h2>
            <p className="panel-note">From recorded usage. Swarm runs are separate because their upstream provider is not stored here.</p>
          </div>
        </div>
        <div id="settings-provider-costs" className="settings-card">
          {providers === null
            ? "Loading provider costs…"
            : providers.length === 0
              ? "No recorded usage in this period."
              : providers.map((item) => (
                  <div key={item.group} className="provider-cost-row">
                    <span>{`${providerName(item.group)} · ${number(item.calls)} calls${item.unpriced_calls ? ` · ${number(item.unpriced_calls)} unpriced` : ""}`}</span>
                    <strong>{money(item.estimated_cost_usd)}</strong>
                  </div>
                ))}
        </div>
      </section>
    </>
  );
}
