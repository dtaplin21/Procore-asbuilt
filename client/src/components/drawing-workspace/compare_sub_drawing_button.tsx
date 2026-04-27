type Props = {
  onClick: () => void;
  disabled?: boolean;
};

export default function CompareSubDrawingButton({
  onClick,
  disabled = false,
}: Props) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="w-full rounded-lg bg-primary px-4 py-3 text-sm font-medium text-primary-foreground transition hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-60"
      data-testid="compare-sub-drawing-button"
    >
      Compare a sub drawing
    </button>
  );
}
