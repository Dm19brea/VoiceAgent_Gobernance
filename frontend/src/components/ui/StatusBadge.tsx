export type StatusVariant = "success" | "danger" | "neutral";

const STATUS_VARIANT_MAP: Record<string, StatusVariant> = {
  passed: "success",
  failed: "danger",
};

const VARIANT_CLASSES: Record<StatusVariant, string> = {
  success: "bg-success-surface text-success-fg",
  danger: "bg-danger-surface text-danger-fg",
  neutral: "bg-surface-muted text-muted",
};

export function StatusBadge({
  status,
  className = "",
}: Readonly<{ status: string; className?: string }>) {
  const variant = STATUS_VARIANT_MAP[status] ?? "neutral";

  return (
    <span
      data-testid="status-badge"
      className={`inline-flex items-center rounded-[var(--radius-badge)] px-2 py-0.5 text-xs font-medium ${VARIANT_CLASSES[variant]} ${className}`}
    >
      {status}
    </span>
  );
}
