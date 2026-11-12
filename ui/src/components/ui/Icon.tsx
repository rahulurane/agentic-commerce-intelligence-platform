// Hand-written inline SVG icon set (24x24, stroke based). No icon package is used.
const PATHS = {
  shield: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3z",
  network:
    "M12 5v6M12 11l-6 6M12 11l6 6M12 5m-2 0a2 2 0 104 0 2 2 0 10-4 0M6 17m-2 0a2 2 0 104 0 2 2 0 10-4 0M18 17m-2 0a2 2 0 104 0 2 2 0 10-4 0",
  scale: "M12 4v16M6 20h12M4 8h16M7 8l-3 6a3 3 0 006 0L7 8zM17 8l-3 6a3 3 0 006 0l-3-6z",
  route:
    "M6 19a2 2 0 100-4 2 2 0 000 4zM18 9a2 2 0 100-4 2 2 0 000 4zM8 17h6a3 3 0 000-6h-4a3 3 0 010-6h6",
  receipt: "M6 3h12v18l-3-2-3 2-3-2-3 2V3zM9 8h6M9 12h6",
  bolt: "M13 3L5 14h6l-1 7 8-11h-6l1-7z",
  user: "M12 12a4 4 0 100-8 4 4 0 000 8zM4 21c0-4 4-6 8-6s8 2 8 6",
  device: "M7 3h10a1 1 0 011 1v16a1 1 0 01-1 1H7a1 1 0 01-1-1V4a1 1 0 011-1zM11 18h2",
  card: "M3 6h18v12H3V6zM3 10h18M7 15h4",
  wallet: "M4 7h14a2 2 0 012 2v9a2 2 0 01-2 2H6a2 2 0 01-2-2V7zM4 7l12-3v3M16 13h2",
  "check-circle": "M12 21a9 9 0 100-18 9 9 0 000 18zM8 12l3 3 5-6",
  "alert-triangle": "M12 4l9 16H3L12 4zM12 10v4M12 17v.5",
  "x-circle": "M12 21a9 9 0 100-18 9 9 0 000 18zM9 9l6 6M15 9l-6 6",
  help: "M12 21a9 9 0 100-18 9 9 0 000 18zM9.5 9.5a2.5 2.5 0 114 2c-1 .7-1.5 1.2-1.5 2.5M12 17v.5",
  info: "M12 21a9 9 0 100-18 9 9 0 000 18zM12 11v6M12 7.5v.5",
  copy: "M9 9h10v11H9V9zM5 15V4h10",
  chevron: "M9 6l6 6-6 6",
  sun: "M12 16a4 4 0 100-8 4 4 0 000 8zM12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5",
  moon: "M20 14.5A8 8 0 019.5 4 8 8 0 1020 14.5z",
  play: "M7 4l13 8-13 8V4z",
  refresh: "M20 11a8 8 0 00-14-4M4 5v4h4M4 13a8 8 0 0014 4M20 19v-4h-4",
  link: "M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1 1M14 10a4 4 0 00-5.7 0l-3 3a4 4 0 005.7 5.7l1-1",
  layers: "M12 3l9 5-9 5-9-5 9-5zM3 13l9 5 9-5M3 17.5l9 5 9-5",
  lock: "M6 11h12v10H6V11zM8 11V8a4 4 0 118 0v3",
} as const;

export type IconName = keyof typeof PATHS;

interface Props {
  name: IconName;
  size?: number;
  /** Accessible label. Omit for purely decorative icons (hidden from assistive tech). */
  label?: string;
  className?: string;
}

export default function Icon({ name, size = 20, label, className }: Props) {
  return (
    <svg
      className={className ? `icon ${className}` : "icon"}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
