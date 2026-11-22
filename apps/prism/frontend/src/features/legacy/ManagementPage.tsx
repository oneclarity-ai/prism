import { dateTime } from "./format";
import { useLegacyData } from "./LegacyDataProvider";
import { ActionButton, Badge, Item, ListBox } from "./parts";

export function ManagementPage() {
  const { data, nameFor, openRecord } = useLegacyData();
  const totals = data.totals;
  return (
    <>
      <div className="view-toolbar">
        <p className="panel-note">Add employees, projects, tasks, and other records by hand.</p>
        <button id="new-record-button" className="button" type="button" onClick={openRecord}>
          New record
        </button>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <h2>Open escalations</h2>
          <Badge id="escalations-count">{totals?.escalations ?? 0}</Badge>
        </div>
        <ListBox
          id="escalations-list"
          items={data.escalations}
          empty="No open escalations."
          render={(escalation) => (
            <Item
              key={escalation.id}
              title={escalation.reason}
              meta={`${escalation.escalation_type.replaceAll("_", " ")} · ${escalation.severity}`}
              actions={
                <>
                  <ActionButton label="Acknowledge" action="acknowledge-escalation" id={escalation.id} />
                  <ActionButton label="Resolve" action="resolve-escalation" id={escalation.id} />
                </>
              }
            />
          )}
        />
      </section>
      <section className="panel">
        <div className="panel-heading">
          <h2>What is blocked</h2>
          <Badge id="blockers-count">{totals?.blockers ?? 0}</Badge>
        </div>
        <ListBox
          id="blockers-list"
          items={data.blockers}
          empty="No open blockers."
          render={(blocker) => {
            const dependencyOwner = (blocker.dependency_owner_ids || []).map(nameFor).join(", ") || "Not assigned";
            return (
              <Item
                key={blocker.id}
                title={blocker.description}
                meta={`Blocked: ${nameFor(blocker.blocked_employee_id)} · Dependency owner: ${dependencyOwner} · Severity: ${blocker.severity}`}
                actions={
                  <>
                    <ActionButton label="Mark resolved" action="resolve-blocker" id={blocker.id} />
                    {blocker.dependency_owner_id ? (
                      <ActionButton label="Record Teams follow-up" action="blocker-follow-up" id={blocker.id} />
                    ) : null}
                  </>
                }
              />
            );
          }}
        />
      </section>
      <section className="panel">
        <div className="panel-heading">
          <h2>Commitments &amp; deadlines</h2>
          <Badge id="commitments-count">{totals?.commitments ?? 0}</Badge>
        </div>
        <ListBox
          id="commitments-list"
          items={data.commitments}
          empty="No open commitments."
          render={(commitment) => (
            <Item
              key={commitment.id}
              title={commitment.description}
              meta={`Responsible: ${nameFor(commitment.employee_id)} · Deadline: ${dateTime(commitment.deadline)} · Status: ${commitment.status}`}
              actions={
                <>
                  <ActionButton label="Mark missed" action="mark-missed" id={commitment.id} />
                  <ActionButton label="Missed + revised ETA" action="revise-commitment" id={commitment.id} />
                </>
              }
            />
          )}
        />
      </section>
      <section className="panel">
        <div className="panel-heading">
          <h2>Today&apos;s updates</h2>
          <Badge id="updates-count">{totals?.updates ?? 0}</Badge>
        </div>
        <ListBox
          id="updates-list"
          items={data.updates}
          empty="No updates received today."
          render={(update) => <Item key={update.id} title={nameFor(update.employee_id)} meta={update.today_summary} />}
        />
      </section>
    </>
  );
}
