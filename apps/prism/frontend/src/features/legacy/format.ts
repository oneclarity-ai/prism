export const today = (): string => new Date().toISOString().slice(0, 10);

export function humanize(value: unknown): string {
  return String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function dateTime(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "No deadline";
}

export function categoryLabel(category: string): string {
  const labels: Record<string, string> = {
    team: "Team context",
    work: "Current work",
    people: "Person or role",
    communication: "Communication preference",
    escalation: "Escalation guidance",
    other: "Other",
  };
  return labels[category] || "Other";
}

export function firstName(name: unknown): string {
  return String(name || "").trim().split(/\s+/)[0] || "Team member";
}

export function initials(name: unknown): string {
  return (
    String(name || "M")
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((part) => part[0])
      .join("")
      .toUpperCase() || "M"
  );
}

interface FactLike {
  subject_text?: string | null;
  subject_type?: string | null;
  predicate?: string | null;
  object_text?: string | null;
  object_type?: string | null;
}

export function factText(fact: FactLike): string {
  return `${fact.subject_text || fact.subject_type} ${String(fact.predicate || "").replaceAll("_", " ")} ${fact.object_text || fact.object_type || ""}`;
}
