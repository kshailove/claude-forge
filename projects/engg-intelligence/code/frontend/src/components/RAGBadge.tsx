import { cn } from "@/lib/utils";
import type { RAG } from "@/lib/types";

interface RAGBadgeProps {
  rag: RAG | null | undefined;
  showLabel?: boolean;
  size?: "sm" | "md" | "lg";
  className?: string;
}

const RAG_CONFIG: Record<RAG, { dot: string; label: string; text: string }> = {
  green: {
    dot: "bg-rag-green",
    label: "Green",
    text: "text-green-700",
  },
  amber: {
    dot: "bg-rag-amber",
    label: "Amber",
    text: "text-amber-700",
  },
  red: {
    dot: "bg-rag-red",
    label: "Red",
    text: "text-red-700",
  },
};

const DOT_SIZES: Record<string, string> = {
  sm: "h-2 w-2",
  md: "h-3 w-3",
  lg: "h-4 w-4",
};

export function RAGBadge({
  rag,
  showLabel = false,
  size = "md",
  className,
}: RAGBadgeProps) {
  if (!rag) {
    return (
      <span className={cn("flex items-center gap-1.5", className)}>
        <span className={cn("rounded-full bg-gray-300", DOT_SIZES[size])} />
        {showLabel && <span className="text-sm text-gray-500">Unknown</span>}
      </span>
    );
  }

  const config = RAG_CONFIG[rag];

  return (
    <span className={cn("flex items-center gap-1.5", className)}>
      <span className={cn("rounded-full", config.dot, DOT_SIZES[size])} />
      {showLabel && (
        <span className={cn("text-sm font-medium", config.text)}>
          {config.label}
        </span>
      )}
    </span>
  );
}
