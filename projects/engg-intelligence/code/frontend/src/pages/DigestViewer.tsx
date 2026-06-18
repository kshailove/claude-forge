import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Mail } from "lucide-react";
import { useDigestDetail } from "@/hooks/useDigests";
import { PageLoader } from "@/components/LoadingSpinner";

/**
 * DigestViewer — renders a single digest's HTML in a sandboxed iframe.
 *
 * The iframe uses srcDoc + sandbox="allow-same-origin" to safely render
 * untrusted HTML without risk of script execution or navigation.
 * Never uses dangerouslySetInnerHTML.
 */
export function DigestViewer() {
  const { digestId } = useParams<{ digestId: string }>();
  const navigate = useNavigate();
  const { data, isLoading, error } = useDigestDetail(digestId ?? null);

  if (isLoading) return <PageLoader />;

  if (error || !data) {
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-sm text-muted-foreground">
          Failed to load digest. It may have been deleted or you do not have
          access.
        </p>
      </div>
    );
  }

  const statusColour =
    data.delivery_status === "sent"
      ? "text-green-600"
      : data.delivery_status === "failed"
      ? "text-red-600"
      : "text-amber-600";

  return (
    <div>
      {/* Header bar */}
      <div className="mb-4 flex items-center justify-between">
        <button
          onClick={() => navigate("/digests")}
          className="flex items-center gap-1.5 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Digests
        </button>

        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          <div className="flex items-center gap-1.5">
            <Mail className="h-4 w-4" />
            <span className="font-medium text-foreground">{data.subject}</span>
          </div>
          {data.sent_at && (
            <span>
              Sent{" "}
              {new Date(data.sent_at).toLocaleDateString("en-US", {
                weekday: "short",
                month: "short",
                day: "numeric",
                year: "numeric",
              })}
            </span>
          )}
          <span className={statusColour}>
            {data.delivery_status.charAt(0).toUpperCase() +
              data.delivery_status.slice(1)}
          </span>
        </div>
      </div>

      {/* Sandboxed iframe — safe rendering of digest HTML */}
      <div className="overflow-hidden rounded-xl border border-border shadow-sm">
        <iframe
          title={data.subject}
          srcDoc={data.html_content}
          sandbox="allow-same-origin"
          style={{
            width: "100%",
            height: "800px",
            border: "none",
            display: "block",
          }}
        />
      </div>
    </div>
  );
}
