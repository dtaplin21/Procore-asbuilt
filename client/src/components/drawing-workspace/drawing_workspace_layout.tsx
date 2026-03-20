import { ReactNode } from "react";

type Props = {
  header: ReactNode;
  viewer: ReactNode;
  sidebar: ReactNode;
};

export default function DrawingWorkspaceLayout({ header, viewer, sidebar }: Props) {
  return (
    <div className="min-h-screen bg-slate-50 p-4">
      <div className="mb-4">{header}</div>

      <div className="grid min-h-[80vh] grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="min-h-[70vh]">{viewer}</div>
        <aside className="flex flex-col gap-4">{sidebar}</aside>
      </div>
    </div>
  );
}
