import { cn } from "@/lib/utils";

interface LoadingSpinnerProps {
  size?: "sm" | "md" | "lg";
  className?: string;
  label?: string;
}

const SIZE_CLASSES: Record<string, string> = {
  sm: "h-4 w-4 border-2",
  md: "h-8 w-8 border-2",
  lg: "h-12 w-12 border-4",
};

export function LoadingSpinner({
  size = "md",
  className,
  label = "Loading...",
}: LoadingSpinnerProps) {
  return (
    <div
      className={cn("flex flex-col items-center justify-center gap-2", className)}
      role="status"
      aria-label={label}
    >
      <div
        className={cn(
          "animate-spin rounded-full border-border border-t-primary",
          SIZE_CLASSES[size]
        )}
      />
      <span className="sr-only">{label}</span>
    </div>
  );
}

export function PageLoader() {
  return (
    <div className="flex h-64 w-full items-center justify-center">
      <LoadingSpinner size="lg" />
    </div>
  );
}
