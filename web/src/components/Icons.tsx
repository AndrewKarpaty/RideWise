/** Inline stroke icons. Decorative ones are hidden from assistive tech; any
 *  icon that carries meaning on its own gets a title via `label`. */

interface IconProps {
  size?: number;
  label?: string;
  className?: string;
}

function Svg({
  size = 18,
  label,
  children,
  fill = "none",
  width,
}: IconProps & { children: React.ReactNode; fill?: string; width?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={fill}
      stroke="currentColor"
      strokeWidth={width ?? 2.2}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      {children}
    </svg>
  );
}

export const ArrowRight = (p: IconProps) => (
  <Svg {...p} width={3}>
    <path d="M5 12h13" />
    <path d="m12 5 7 7-7 7" />
  </Svg>
);

export const Wheel = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 12a9 9 0 0 1 18 0" />
    <circle cx="12" cy="17" r="3.4" />
    <path d="M12 13.6V7" />
  </Svg>
);

export const Camera = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 17V8a2 2 0 0 1 2-2h2.5l1.5-2h6l1.5 2H19a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
    <circle cx="12" cy="12.5" r="3.4" />
  </Svg>
);

export const Fuel = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5 21V5a2 2 0 0 1 2-2h5a2 2 0 0 1 2 2v16" />
    <path d="M3 21h13M7 7h5" />
    <path d="M14 9h3a2 2 0 0 1 2 2v6a1.5 1.5 0 0 0 3 0v-6l-2.5-4" />
  </Svg>
);

export const Sun = (p: IconProps) => (
  <Svg {...p} width={2}>
    <circle cx="12" cy="12" r="4.2" />
    <path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.2 5.2l1.6 1.6M17.2 17.2l1.6 1.6M18.8 5.2l-1.6 1.6M6.8 17.2l-1.6 1.6" />
  </Svg>
);

export const Cloud = (p: IconProps) => (
  <Svg {...p} width={2}>
    <path d="M17 18a4 4 0 0 0-.8-7.9A6 6 0 0 0 4.5 11A3.5 3.5 0 0 0 5 18z" />
  </Svg>
);

export const Rain = (p: IconProps) => (
  <Svg {...p} width={2}>
    <path d="M17 15a4 4 0 0 0-.8-7.9A6 6 0 0 0 4.5 8A3.5 3.5 0 0 0 5 15z" />
    <path d="M8 19l-.8 2M12 19l-.8 2M16 19l-.8 2" />
  </Svg>
);

export const Snow = (p: IconProps) => (
  <Svg {...p} width={2}>
    <path d="M17 15a4 4 0 0 0-.8-7.9A6 6 0 0 0 4.5 8A3.5 3.5 0 0 0 5 15z" />
    <path d="M8 19v2M12 19v2M16 19v2M7 20h2M11 20h2M15 20h2" />
  </Svg>
);

export const Storm = (p: IconProps) => (
  <Svg {...p} width={2}>
    <path d="M17 14a4 4 0 0 0-.8-7.9A6 6 0 0 0 4.5 7A3.5 3.5 0 0 0 5 14z" />
    <path d="m12 14-2 4h3l-1.5 4" />
  </Svg>
);

export const Fog = (p: IconProps) => (
  <Svg {...p} width={2}>
    <path d="M17 13a4 4 0 0 0-.8-7.9A6 6 0 0 0 4.5 6A3.5 3.5 0 0 0 5 13z" />
    <path d="M5 17h14M7 20h10" />
  </Svg>
);

export const Warning = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 9v5" />
    <path d="M12 17.5v.5" />
    <path d="M10.3 3.8 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.8a2 2 0 0 0-3.4 0z" />
  </Svg>
);

export const Download = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 3v12" />
    <path d="m7 11 5 5 5-5" />
    <path d="M4 20h16" />
  </Svg>
);

export const Check = (p: IconProps) => (
  <Svg {...p} width={3}>
    <path d="m5 13 4 4L19 7" />
  </Svg>
);

export const Plus = (p: IconProps) => (
  <Svg {...p} width={2.8}>
    <path d="M12 5v14M5 12h14" />
  </Svg>
);

export const Trash = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14" />
  </Svg>
);

export const Viewpoint = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 17l6-7 4 4 3-3 5 6z" />
    <circle cx="8" cy="7" r="2" />
  </Svg>
);

/** The WMO weather code groups that matter to a rider. */
export function WeatherIcon({ code, size = 22 }: { code: number; size?: number }) {
  if (code >= 95) return <Storm size={size} />;
  if ([71, 73, 75, 77, 85, 86, 66, 67, 56, 57].includes(code)) return <Snow size={size} />;
  if (code >= 51) return <Rain size={size} />;
  if (code === 45 || code === 48) return <Fog size={size} />;
  if (code <= 1) return <Sun size={size} />;
  return <Cloud size={size} />;
}

export function weatherColour(code: number): string {
  if (code >= 95) return "var(--stop)";
  if ([71, 73, 75, 77, 85, 86, 66, 67, 56, 57].includes(code)) return "var(--brand)";
  if (code >= 51) return "var(--brand-dark)";
  if (code === 45 || code === 48) return "var(--muted)";
  if (code <= 1) return "#b9500f";
  return "var(--muted)";
}
