import { Button, Chip, DataTable, Empty, Icon, TitleCell } from "@/components/ui";
import { age, words } from "@/lib/format";
import type { WorkspacePageProps, PageContext } from "./shared";

export function targetsActions(ctx: PageContext) {
  return <Button text="Add target" glyph="plus" className="button" onClick={() => ctx.editTarget()} />;
}

export function TargetsPage({ ctx }: WorkspacePageProps) {
  if (!ctx.data.targets.length) return <Empty title="No target apps yet" description="Add a web app for your Prisms to work with." glyph="globe" />;
  return (
    <DataTable
      headers={["App", "Environment", "Login", "Tasks", "Added", ""]}
      rows={ctx.data.targets.map((item) => ({
        key: item.id,
        cells: [
          <TitleCell title={item.name} subtitle={item.base_url} onClick={() => ctx.editTarget(item)} />,
          <Chip tone={item.environment === "production" ? "red" : "gray"}>{words(item.environment)}</Chip>,
          <span className={item.has_test_login ? "workspace-positive" : "subtle"}>{item.has_test_login ? "Stored" : "None"}</span>,
          ctx.data.tasks.filter((task) => task.target_app_id === item.id).length,
          age(item.created_at),
          <div className="workspace-row-actions">
            <Button glyph="ellipsis" className="icon-button" title={`Edit ${item.name}`} onClick={() => ctx.editTarget(item)} />
            <Button glyph="trash-2" className="icon-button danger" title={`Delete ${item.name}`} onClick={() => ctx.remove("targets", item)} />
          </div>,
        ],
      }))}
    />
  );
}

export function secretsActions(ctx: PageContext) {
  return <Button text="New secret" glyph="plus" className="button" onClick={() => ctx.editSecret()} />;
}

export function SecretsPage({ ctx }: WorkspacePageProps) {
  return (
    <>
      <div className="workspace-vault">
        <Icon name="shield-check" />
        <div>
          <strong>Write-only vault</strong>
          <p className="panel-note">Values are encrypted by the computer service and never shown here. Saved target logins appear under their target_login scope.</p>
        </div>
      </div>
      {!ctx.data.secrets.length ? (
        <Empty title="No secrets yet" description="Store credentials that your Prisms need." glyph="key-round" />
      ) : (
        <DataTable
          headers={["Name", "Scope", "Value", "Created", ""]}
          rows={ctx.data.secrets.map((item) => ({
            key: item.id,
            cells: [
              <TitleCell title={item.name} />,
              <Chip>{item.scope || "general"}</Chip>,
              <span className="workspace-secret-mask">••••••••</span>,
              age(item.created_at),
              <Button glyph="trash-2" className="icon-button danger" title={`Delete ${item.name}`} onClick={() => ctx.remove("secrets", item)} />,
            ],
          }))}
        />
      )}
    </>
  );
}
