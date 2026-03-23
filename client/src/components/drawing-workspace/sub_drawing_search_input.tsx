type Props = {
  value: string;
  onChange: (value: string) => void;
};

export default function SubDrawingSearchInput({ value, onChange }: Props) {
  return (
    <div>
      <label
        htmlFor="sub-drawing-search"
        className="mb-2 block text-sm font-medium text-slate-700"
      >
        Search sub drawings
      </label>

      <input
        id="sub-drawing-search"
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Search by drawing name..."
        className="w-full rounded-lg border px-3 py-2 text-sm outline-none ring-0 transition focus:border-slate-400"
        data-testid="sub-drawing-search-input"
      />
    </div>
  );
}
