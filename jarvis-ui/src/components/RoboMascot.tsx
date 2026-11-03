import React from "react";
import { JarvisMood } from "../types";

interface RoboMascotProps {
  mood: JarvisMood;
  size?: number;
  className?: string;
}

export const RoboMascot: React.FC<RoboMascotProps> = ({ mood, size = 32, className = "" }) => {
  // Determine eye color and glow by mood
  let eyeColor = "#f5f5f5";
  let auraGlow = "rgba(255, 255, 255, 0.1)";

  if (mood === "listening") {
    eyeColor = "#f43f5e";
    auraGlow = "rgba(244, 63, 94, 0.4)";
  } else if (mood === "thinking") {
    eyeColor = "#f59e0b";
    auraGlow = "rgba(245, 158, 11, 0.4)";
  } else if (mood === "speaking") {
    eyeColor = "#10b981";
    auraGlow = "rgba(16, 185, 129, 0.4)";
  } else if (mood === "approval") {
    eyeColor = "#a855f7";
    auraGlow = "rgba(168, 85, 247, 0.4)";
  }

  return (
    <div
      className={`relative flex items-center justify-center select-none ${className}`}
      style={{ width: size, height: size }}
    >
      {/* Outer ambient glow ring */}
      <div
        className="absolute inset-0 rounded-full transition-all duration-500 blur-sm pointer-events-none"
        style={{ backgroundColor: auraGlow }}
      />

      <svg
        width={size}
        height={size}
        viewBox="0 0 64 64"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="relative z-10"
      >
        {/* Antenna */}
        <circle cx="32" cy="7" r="3" fill="#525252" />
        <rect x="30.5" y="10" width="3" height="6" rx="1.5" fill="#525252" />

        {/* Head Shell */}
        <rect
          x="10"
          y="15"
          width="44"
          height="36"
          rx="14"
          fill="#171717"
          stroke="#333333"
          strokeWidth="2"
        />

        {/* Visor Screen */}
        <rect
          x="15"
          y="20"
          width="34"
          height="24"
          rx="8"
          fill="#080808"
        />

        {/* Expression Eyes */}
        {mood === "online" && (
          <>
            <circle cx="26" cy="32" r="3.5" fill={eyeColor} />
            <circle cx="38" cy="32" r="3.5" fill={eyeColor} />
          </>
        )}

        {mood === "listening" && (
          <>
            <ellipse cx="26" cy="32" rx="4" ry="5" fill={eyeColor} />
            <ellipse cx="38" cy="32" rx="4" ry="5" fill={eyeColor} />
          </>
        )}

        {mood === "thinking" && (
          <>
            <rect x="22" y="30.5" width="8" height="3" rx="1.5" fill={eyeColor} />
            <rect x="34" y="30.5" width="8" height="3" rx="1.5" fill={eyeColor} />
          </>
        )}

        {mood === "speaking" && (
          <>
            {/* Happy curved eyes */}
            <path
              d="M23 33C23 30 29 30 29 33"
              stroke={eyeColor}
              strokeWidth="2.5"
              strokeLinecap="round"
            />
            <path
              d="M35 33C35 30 41 30 41 33"
              stroke={eyeColor}
              strokeWidth="2.5"
              strokeLinecap="round"
            />
          </>
        )}

        {mood === "approval" && (
          <>
            <circle cx="26" cy="31" r="4" fill={eyeColor} />
            <circle cx="38" cy="31" r="4" fill={eyeColor} />
          </>
        )}

        {/* Ears */}
        <rect x="5" y="27" width="5" height="12" rx="2.5" fill="#333333" />
        <rect x="54" y="27" width="5" height="12" rx="2.5" fill="#333333" />
      </svg>
    </div>
  );
};
