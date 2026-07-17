export type SpinnerSize = "sm" | "md" | "lg";

const SIZE_CLASSES: Record<SpinnerSize, string> = {
  sm: "h-4 w-4 border-2",
  md: "h-6 w-6 border-2",
  lg: "h-10 w-10 border-[3px]",
};

export function Spinner({
  size = "md",
  label = "Loading",
}: Readonly<{ size?: SpinnerSize; label?: string }>) {
  return (
    <span
      role="status"
      aria-busy="true"
      aria-label={label}
      data-testid="spinner"
      className={`inline-block animate-spin-slow rounded-full border-border border-t-brand ${SIZE_CLASSES[size]}`}
    />
  );
}
