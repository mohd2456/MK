/**
 * GaugeCard Component
 * ====================
 * Circular gauge display for CPU, RAM, Disk, Network.
 * Shows percentage with colored ring and label/subtitle.
 */

import { cn } from "@/lib/utils";

interface GaugeCardProps {
  label: string;
  value: number; // 0-100 for percentage, or raw value for display
  displayValue: string; // Formatted display (e.g., "47%", "120 MB/s")
  subtitle: string; // e.g., "12 cores", "32/64 GB"
  icon: React.ReactNode;
  /** Color of the ring - auto picks based on value */
  variant?: "auto" | "accent" | "success" | "warning" | "error";
}

export function GaugeCard({
  label,
  value,
  displayValue,
  subtitle,
  icon,
  variant = "auto",
}: GaugeCardProps) {
  const percent = Math.min(100, Math.max(0, value));

  // Auto-color thresholds
  const resolvedColor =
    variant === "auto"
      ? percent >= 90
        ? "error"
        : percent >= 75
          ? "warning"
          : "accent"
      : variant;

  const colorMap = {
    accent: { stroke: "#00d4ff", bg: "rgba(0,212,255,0.08)" },
    success: { stroke: "#00e676", bg: "rgba(0,230,118,0.08)" },
    warning: { stroke: "#ffab00", bg: "rgba(255,171,0,0.08)" },
    error: { stroke: "#ff5252", bg: "rgba(255,82,82,0.08)" },
  };

  const colors = colorMap[resolvedColor];

  // SVG ring parameters
  const size = 80;
  const strokeWidth = 6;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference - (percent / 100) * circumference;

  return (
    <div
      className={cn(
        "rounded-[8px] border border-mk-border bg-mk-surface p-4",
        "flex flex-col items-center gap-3",
        "hover:border-mk-border-strong transition-colors duration-200"
      )}
    >
      {/* Gauge ring */}
      <div className="relative">
        <svg width={size} height={size} className="-rotate-90">
          {/* Background ring */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="currentColor"
            strokeWidth={strokeWidth}
            className="text-mk-border"
          />
          {/* Value ring */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={colors.stroke}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            className="transition-all duration-700 ease-out"
            style={{ filter: `drop-shadow(0 0 4px ${colors.stroke}40)` }}
          />
        </svg>
        {/* Center icon/value */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-mk-text-muted" style={{ color: colors.stroke }}>
            {icon}
          </span>
        </div>
      </div>

      {/* Label and value */}
      <div className="text-center">
        <p className="text-xs text-mk-text-muted font-medium uppercase tracking-wider">
          {label}
        </p>
        <p className="text-xl font-bold text-mk-text-primary mt-0.5">
          {displayValue}
        </p>
        <p className="text-xs text-mk-text-muted mt-0.5">{subtitle}</p>
      </div>
    </div>
  );
}
