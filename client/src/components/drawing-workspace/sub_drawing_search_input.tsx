type Props = {
  value: string;
  onChange: (value: string) => void;
};

export default function SubDrawingSearchInput({ value, onChange }: Props) {
  return (
    <div>
      <label
        htmlFor="sub-drawing-search"
        className="mb-2 block text-sm font-medium text-foreground"
      >
        Search sub drawings
      </label>

      <input
        id="sub-drawing-search"
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Search by drawing name..."
        className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none ring-0 transition focus-visible:border-primary focus-visible:ring-1 focus-visible:ring-ring"
        data-testid="sub-drawing-search-input"
      />
    </div>
  );
}
