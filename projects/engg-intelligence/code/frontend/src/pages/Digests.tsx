import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Eye, Mail, RefreshCw } from "lucide-react";
import { useDigestsList, useDigestPreview } from "@/hooks/useDigests";
import { PageLoader } from "@/components/LoadingSpinner";
import type { DigestSummary } from "@/lib/types";

/**
 * Digests — lists past weekly digests + preview button for next Monday's email.
 */
export function Digests() {
  const navigate = useNavigate();
  const { data, isLoading, error } = useDigestsList();
  const [previewOpen, setPreviewOpen] = useState(false);

  if (isLoading) return <PageLoader />;

  if (error) {
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-sm text-muted-foreground">
          Failed to load digests. Please try again.
        </p>
      </div>
    );
  }

  return (
    <div>
      {/* Page header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Weekly Digests</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Your personalised engineering health summaries, delivered every
            Monday morning.
          </p>
        </div>
        <button
          onClick={() => setPreviewOpen(true)}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
        >
          <Eye className="h-4 w-4" />
          Preview Next Monday's Digest
        </button>
      </div>

      {/* Preview panel */}
      {previewOpen && (
        <DigestPreviewPanel onClose={() => setPreviewOpen(false)} />
      )}

      {/* Digest list */}
      {!data || data.digests.length === 0 ? (
        <div className="flex h-64 flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border">
          <Mail className="h-8 w-8 text-muted-foreground/50" />
          <p className="font-medium">No digests yet</p>
          <p className="text-sm text-muted-foreground">
            Your first digest will arrive next Monday at 06:00 UTC.
          </p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-muted/40">
              <tr>
                <th className="px-6 py-4 text-left font-medium text-muted-foreground">
                  Subject
                </th>
                <th className="px-6 py-4 text-left font-medium text-muted-foreground">
                  Sent
                </th>
                <th className="px-6 py-4 text-center font-medium text-muted-foreground">
                  Status
                </th>
                <th className="px-6 py-4 text-right font-medium text-muted-foreground">
                  Action
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {data.digests.map((digest) => (
                <DigestRow
                  key={digest.digest_id}
                  digest={digest}
                  onView={() => navigate(`/digests/${digest.digest_id}`)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Digest row component
// ---------------------------------------------------------------------------

function DigestRow({
  digest,
  onView,
}: {
  digest: DigestSummary;
  onView: () => void;
}) {
  const sentDate = digest.sent_at
    ? new Date(digest.sent_at).toLocaleDateString("en-US", {
        weekday: "short",
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : "—";

  return (
    <tr
      className="cursor-pointer transition-colors hover:bg-muted/30"
      onClick={onView}
    >
      <td className="px-6 py-4">
        <div>
          <p className="font-medium">{digest.subject}</p>
          <p className="mt-0.5 max-w-md truncate text-xs text-muted-foreground">
            {digest.preview_text}
          </p>
        </div>
      </td>
      <td className="px-6 py-4 text-muted-foreground">{sentDate}</td>
      <td className="px-6 py-4">
        <div className="flex justify-center">
          <StatusBadge status={digest.delivery_status} />
        </div>
      </td>
      <td className="px-6 py-4 text-right">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onView();
          }}
          className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/10 transition-colors"
        >
          <Eye className="h-3.5 w-3.5" />
          View
        </button>
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

function StatusBadge({ status }: { status: string }) {
  const variants: Record<string, string> = {
    sent: "bg-green-100 text-green-700",
    failed: "bg-red-100 text-red-700",
    pending: "bg-amber-100 text-amber-700",
  };
  const cls = variants[status] ?? "bg-muted text-muted-foreground";
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}
    >
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Preview panel — live digest rendered in a sandboxed iframe
// ---------------------------------------------------------------------------

function DigestPreviewPanel({ onClose }: { onClose: () => void }) {
  const { data, isLoading, error, refetch } = useDigestPreview(true);

  return (
    <div className="mb-6 overflow-hidden rounded-xl border border-border bg-card shadow-sm">
      {/* Panel header */}
      <div className="flex items-center justify-between border-b border-border bg-muted/40 px-6 py-4">
        <div>
          <h2 className="font-semibold">Next Monday's Digest — Preview</h2>
          <p className="text-xs text-muted-foreground">
            This preview is generated live and not stored.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => refetch()}
            className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs text-muted-foreground hover:bg-accent transition-colors"
            title="Refresh preview"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </button>
          <button
            onClick={onClose}
            className="rounded-md px-3 py-1.5 text-xs text-muted-foreground hover:bg-accent transition-colors"
          >
            Close
          </button>
        </div>
      </div>

      {/* Content area */}
      {isLoading && (
        <div className="flex h-40 items-center justify-center">
          <p className="text-sm text-muted-foreground">
            Generating preview…
          </p>
        </div>
      )}

      {error && (
        <div className="flex h-40 items-center justify-center">
          <p className="text-sm text-muted-foreground">
            Failed to generate preview. Please try again.
          </p>
        </div>
      )}

      {data && (
        <iframe
          title="Digest Preview"
          srcDoc={data.html_content}
          sandbox="allow-same-origin"
          style={{
            width: "100%",
            height: "700px",
            border: "none",
            display: "block",
          }}
        />
      )}
    </div>
  );
}
