"use client";

import { useRouter } from "next/navigation";
import { RequireSession } from "@/components/shell/AppShell";
import { Loading, PageError, StateView } from "@/components/ui";
import { useClient, useResource, useRuntime, useSession } from "@/lib/preview/client-context";

export default function InboxPage() {
  return (
    <RequireSession>
      <Inbox />
    </RequireSession>
  );
}

function Inbox() {
  const { session } = useSession();
  const client = useClient();
  const router = useRouter();
  const api = useRuntime().mode === "http";
  const list = useResource((c) => c.listNotifications(), [session?.persona.employee_id]);
  if (list.loading) return <Loading label="Loading inbox" />;
  if (list.error) return <PageError error={list.error} onRetry={list.reload} />;
  const items = list.data ?? [];
  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Inbox</h1>
          <p>Short notices about work that involves you. Opening one shows the current record, checked again for your access. Marking a notice read doesn&apos;t accept, receive or approve anything.</p>
        </div>
      </div>
      <p className="small muted">
        {api
          ? "Notices arrive through a delivery queue, so one can come a few seconds after the change; the module screens are always current."
          : "Delivery is simulated in this preview. In production these come through a delivery queue, so they can arrive late; the module screens are always current."}
      </p>
      {items.length === 0 ? (
        <StateView title="No notifications">Assignments, review requests and handover publications that involve you appear here.</StateView>
      ) : (
        <ul className="list">
          {items.map((n) => (
            <li key={n.notification_id} className="list-item" aria-current={!n.read_at ? "true" : undefined}>
              <div className="row-between">
                <b>{n.minimal_message}</b>
                <span className="small muted">
                  {n.created_label}
                  {n.read_at ? ", read" : ", unread"}
                </span>
              </div>
              <div className="row">
                <button
                  className="btn btn-small btn-primary"
                  onClick={async () => {
                    await client.markNotificationRead(n.notification_id);
                    router.push(n.resource_href);
                  }}
                >
                  Open
                </button>
                {!n.read_at && (
                  <button className="btn btn-small" onClick={() => void client.markNotificationRead(n.notification_id)}>
                    Mark read
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
