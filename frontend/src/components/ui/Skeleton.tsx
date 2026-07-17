export type SkeletonVariant = "text" | "circle" | "rect";

const VARIANT_CLASSES: Record<SkeletonVariant, string> = {
  text: "h-4 w-full rounded",
  circle: "h-10 w-10 rounded-full",
  rect: "h-24 w-full rounded-[var(--radius-card)]",
};

export function Skeleton({
  variant = "text",
  className = "",
}: Readonly<{ variant?: SkeletonVariant; className?: string }>) {
  return (
    <span
      aria-hidden="true"
      data-testid="skeleton"
      className={`block animate-shimmer bg-[linear-gradient(90deg,var(--color-surface-muted)_25%,var(--color-border)_50%,var(--color-surface-muted)_75%)] bg-[length:200%_100%] ${VARIANT_CLASSES[variant]} ${className}`}
    />
  );
}
