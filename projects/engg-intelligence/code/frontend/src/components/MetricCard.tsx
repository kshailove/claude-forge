import { cn } from "@/lib/utils";

interface MetricCardProps {
  label: string;
  value: string | number | null | undefined;
  unit?: string;
  subtitle?: string;
  className?: string;
  valueClassName?: string;
}

export function MetricCard({
  label,
  value,
  unit,
  subtitle,
  className,
  valueClassName,
}: MetricCardProps) {
  const displayValue = value == null ? "—" : String(value);

  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-card p-4 shadow-sm",
        className
      )}
    >
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className={cn("mt-1 text-2xl font-bold tabular-nums", valueClassName)}>
        {displayValue}
        {unit && value != null && (
          <span className="ml-1 text-sm font-normal text-muted-foreground">
            {unit}
          </span>
        )}
      </p>
      {subtitle && (
        <p className="mt-1 text-xs text-muted-foreground">{subtitle}</p>
      )}
    </div>
  );
}
