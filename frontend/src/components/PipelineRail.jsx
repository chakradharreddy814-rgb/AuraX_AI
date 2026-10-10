// The signature visual element: a literal "assembly line" rail showing which
// station a candidate currently sits at, echoing the agent-pipeline metaphor
// the whole platform is built around.

const STATIONS = [
  { key: 'screened', label: 'Screened', hint: 'Agent 2' },
  { key: 'questions', label: 'Questions Ready', hint: 'Agent 3' },
  { key: 'interviewed', label: 'Interviewed', hint: 'Agent 6' },
  { key: 'evaluated', label: 'Evaluated', hint: 'Agent 5' },
  { key: 'decided', label: 'Decision', hint: 'Agent 7' },
];

function deriveActiveIndex(candidate) {
  if (!candidate) return 0;
  let idx = 0;
  if (candidate.match_score !== undefined && candidate.match_score !== null) idx = 0;
  if (candidate.interview_questions) idx = 1;
  if (candidate.qa_pairs && candidate.qa_pairs.length > 0) idx = 2;
  if (candidate.average_interview_score !== undefined && candidate.average_interview_score !== null) idx = 3;
  if (candidate.next_step || candidate.scheduling) idx = 4;
  return idx;
}

export default function PipelineRail({ candidate, compact = false }) {
  const activeIndex = deriveActiveIndex(candidate);
  const isRejected = candidate?.next_step === 'Reject';

  return (
    <div className={compact ? 'py-2' : 'py-4'}>
      <div className="flex items-center">
        {STATIONS.map((station, i) => {
          const done = i <= activeIndex;
          const isLast = i === STATIONS.length - 1;
          const isCurrent = i === activeIndex;
          let dotColor = done ? 'var(--color-rail)' : 'var(--color-border-soft)';
          if (isCurrent && isLast && isRejected) dotColor = 'var(--color-band-weak)';
          else if (isCurrent && isLast && candidate?.next_step) dotColor = 'var(--color-band-exceptional)';

          return (
            <div key={station.key} className="flex items-center flex-1 last:flex-none">
              <div className="flex flex-col items-center gap-1.5 shrink-0">
                <div
                  className="w-3 h-3 rounded-full ring-4 transition-colors"
                  style={{
                    backgroundColor: dotColor,
                    boxShadow: `0 0 0 4px ${done ? 'color-mix(in srgb, var(--color-rail) 12%, transparent)' : 'transparent'}`,
                  }}
                />
                {!compact && (
                  <div className="text-center">
                    <div className={`text-[11px] font-medium leading-tight ${done ? 'text-ink' : 'text-slate'}`}>
                      {station.label}
                    </div>
                    <div className="text-[10px] font-mono text-slate/70 leading-tight">{station.hint}</div>
                  </div>
                )}
              </div>
              {!isLast && (
                <div
                  className="h-[2px] flex-1 mx-1"
                  style={{ backgroundColor: i < activeIndex ? 'var(--color-rail)' : 'var(--color-border-soft)' }}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
