type Props = {
  title: string;
  description: string;
};

export default function WorkspaceEmptyState({ title, description }: Props) {
  return (
    <div className="rounded-xl border border-dashed bg-white p-6 text-center">
      <div className="text-sm font-medium text-foreground">{title}</div>
      <div className="mt-1 text-sm text-muted-foreground">{description}</div>
    </div>
  );
}
