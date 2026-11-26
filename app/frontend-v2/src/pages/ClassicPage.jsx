import React from 'react';
import { useClassic } from '../lib/classic.jsx';
import { Skeleton } from '../components/ui.jsx';

/** Placeholder for a module that the classic runtime draws over the content area.
 *  Shows a shimmer while the runtime boots (first load only — it stays alive afterwards). */
export default function ClassicPage({ id }) {
  const { ready } = useClassic();
  return (
    <div className="classic-slot" data-module={id}>
      {!ready && (
        <div className="col" style={{ gap: 14 }}>
          <Skeleton h={34} w="38%" />
          <div className="grid g-kpi"><Skeleton h={110} /><Skeleton h={110} /><Skeleton h={110} /><Skeleton h={110} /></div>
          <Skeleton h={320} />
          <div className="faint" style={{ fontSize: 12.5 }}>Loading the module…</div>
        </div>
      )}
    </div>
  );
}
