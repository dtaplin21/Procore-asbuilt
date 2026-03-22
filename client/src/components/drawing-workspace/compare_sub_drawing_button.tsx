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
      className="w-full rounded-lg bg-slate-900 px-4 py-3 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
      data-testid="compare-sub-drawing-button"
    >
      Compare a sub drawing
    </button>
  );
}
