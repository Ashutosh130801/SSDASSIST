import React, { useId } from 'react';

/* RecoverIQ product mark (original design).
   An open "recovery" ring that sweeps into an upward growth arrow, with an insight spark at its
   centre — the Q of RecoverIQ, the cycle of follow-ups, and money coming back up.
   Sits on a clay tile tinted by the active palette; the wordmark sets "IQ" in the theme gradient. */
export const RIQ_PATHS = {
  ring: 'M29.77 16.33 A11 11 0 1 0 32.71 30.16 L37.88 20.45',
  head: 'M33.13 22.57 L37.88 20.45 L38.78 25.57',
  spark: 'M23 20.6 C23.5 23.6 24.4 24.5 27.4 25 C24.4 25.5 23.5 26.4 23 29.4 C22.5 26.4 21.6 25.5 18.6 25 C21.6 24.5 22.5 23.6 23 20.6Z',
};

export function RecoverIQMark({ size = 40, className = '', tile = true }) {
  const id = useId().replace(/:/g, '');
  return (
    <svg className={'riq-mark ' + className} width={size} height={size} viewBox="0 0 48 48" role="img" aria-label="RecoverIQ">
      <defs>
        <linearGradient id={`t${id}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" style={{ stopColor: 'rgb(var(--t-accent2, 14,165,233))' }} />
          <stop offset="100%" style={{ stopColor: 'rgb(var(--t-accent, 37,99,235))' }} />
        </linearGradient>
        <linearGradient id={`h${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#fff" stopOpacity=".42" /><stop offset="55%" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
        <linearGradient id={`g${id}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" style={{ stopColor: 'rgb(var(--t-accent2, 14,165,233))' }} />
          <stop offset="100%" style={{ stopColor: 'rgb(var(--t-accent, 37,99,235))' }} />
        </linearGradient>
      </defs>
      {tile && <>
        <rect x="1" y="1" width="46" height="46" rx="14" fill={`url(#t${id})`} />
        <rect x="1" y="1" width="46" height="46" rx="14" fill={`url(#h${id})`} />
        <rect x="1.5" y="1.5" width="45" height="45" rx="13.5" fill="none" stroke="#fff" strokeOpacity=".35" />
      </>}
      <g fill="none" stroke={tile ? '#fff' : `url(#g${id})`} strokeWidth="3.6" strokeLinecap="round" strokeLinejoin="round">
        <path d={RIQ_PATHS.ring} />
        <path d={RIQ_PATHS.head} />
      </g>
      <path d={RIQ_PATHS.spark} fill={tile ? '#fff' : `url(#g${id})`} />
    </svg>
  );
}

export default function RecoverIQLogo({ size = 40, sub, className = '' }) {
  return (
    <span className={'riq-logo ' + className}>
      <RecoverIQMark size={size} />
      <span className="riq-word">
        <span className="riq-name">Recover<b>IQ</b></span>
        {sub && <span className="riq-sub">{sub}</span>}
      </span>
    </span>
  );
}
