type Props = {
  message: string;
  onRetry?: () => void;
};

export default function WorkspaceErrorState({ message, onRetry }: Props) {
  return (
    <div className="rounded-xl border border-red-200 bg-red-50 p-4">
      <div className="text-sm font-medium text-red-700">Workspace failed to load</div>
      <div className="mt-1 text-sm text-red-600">{message}</div>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 rounded-md border border-red-300 bg-white px-3 py-2 text-sm text-red-700 hover:bg-red-50"
          data-testid="retry-workspace"
        >
          Retry
        </button>
      ) : null}
    </div>
  );
}
