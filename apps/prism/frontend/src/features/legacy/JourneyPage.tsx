import { useState } from "react";
import { agentApi, errorMessage } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import type { Schema } from "@/types";
import { dateTime, firstName } from "./format";
import { useLegacyData } from "./LegacyDataProvider";
import { Badge } from "./parts";
import type { Journey } from "./types";

function JourneyCard({ journey }: { journey: Journey }) {
  const owner = journey.dependency_owner_name || "owner not identified yet";
  const resolved = journey.status === "resolved";
  return (
    <details className="journey-card">
      <summary className="journey-summary">
        <div>
          <span className={`journey-status ${resolved ? "resolved" : "open"}`}>{resolved ? "Resolved" : "Open"}</span>
          <h3>{journey.title}</h3>
          <p>{journey.description}</p>
        </div>
        <div className="journey-people">
          <span>Blocked: {firstName(journey.blocked_employee_name)}</span>
          <span>Dependency: {firstName(owner)}</span>
        </div>
      </summary>
      <div className="journey-history">
        <ol className="journey-events">
          {journey.events.map((event, index) => (
            <li key={index} className={`journey-event ${event.event_type}`}>
              <span className="journey-number">{index + 1}</span>
              <div className="journey-event-body">
                <div className="journey-event-heading">
                  <span className="journey-tag">{event.event_type.replaceAll("_", " ")}</span>
                  <strong>{event.title}</strong>
                  <time>{dateTime(event.occurred_at)}</time>
                </div>
                <p>{event.detail}</p>
              </div>
            </li>
          ))}
        </ol>
        {journey.commitments.length ? (
          <div className="journey-commitments">
            {journey.commitments.map((commitment) => (
              <span key={commitment.id}>
                <strong>{commitment.owner_name}</strong> committed: {commitment.description} · due {dateTime(commitment.deadline)} ·{" "}
                {commitment.status}
              </span>
            ))}
          </div>
        ) : null}
      </div>
    </details>
  );
}

export function JourneyPage() {
  const { setStatus } = useApp();
  const { data, setJourneys } = useLegacyData();
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState(false);

  const createDummyJourney = async () => {
    setBusy(true);
    try {
      const result = await agentApi<Schema<"DummyJourneyResult">>("/api/v1/management/dummy-journey", { method: "POST" });
      setJourneys([result.journey, ...data.journeys.filter((item) => item.blocker_id !== result.blocker_id)]);
      setCreated(true);
      setStatus(result.message);
    } catch (error) {
      setStatus(errorMessage(error), true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel journey-panel">
      <div className="panel-heading">
        <div>
          <h2>Blocker journeys</h2>
          <p className="panel-note">A read-only trail of how Prism handled each blocker across Teams and the database.</p>
        </div>
        <div className="journey-header-actions">
          <button
            id="create-dummy-journey-button"
            className="mini-button"
            type="button"
            data-tooltip="Render an in-memory sample journey. It writes nothing to the database and does not contact Teams."
            disabled={busy}
            onClick={createDummyJourney}
          >
            {created ? "Preview created" : "Preview dummy flow"}
          </button>
          <Badge id="journeys-count">{data.journeys.length}</Badge>
        </div>
      </div>
      {data.journeys.length ? (
        <div id="journeys-list" className="journeys">
          {data.journeys.map((journey) => (
            <JourneyCard key={journey.blocker_id} journey={journey} />
          ))}
        </div>
      ) : (
        <div id="journeys-list" className="journeys empty-state">
          No blocker journeys recorded yet.
        </div>
      )}
    </section>
  );
}
