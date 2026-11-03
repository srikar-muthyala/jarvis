import React from "react";
import { Cpu, HardDrive, Battery } from "lucide-react";
import { TelemetryData } from "../types";

interface StatsCardProps {
  telemetry: TelemetryData;
}

export const StatsCard: React.FC<StatsCardProps> = ({ telemetry }) => {
  const { cpu, ram, batLevel, charging } = telemetry;

  return (
    <div className="flex flex-col justify-between p-3.5 bg-[#171717] hover:bg-[#1a1a1a] transition-colors rounded-2xl border border-white/5 select-none h-full space-y-2">
      {/* Header */}
      <div className="flex items-center justify-between text-xs text-neutral-400">
        <span className="flex items-center gap-1.5 font-medium tracking-wide uppercase text-[11px] text-neutral-400">
          <Cpu className="w-3.5 h-3.5 text-neutral-500" /> Stats
        </span>
        <div className="flex items-center gap-1 text-[11px] font-mono text-neutral-400">
          {charging ? (
            <svg
              viewBox="0 0 24 38"
              className="w-2.5 h-3.5 text-[#6bb13f] animate-pulse drop-shadow-[0_0_6px_rgba(107,177,63,0.8)]"
              fill="currentColor"
            >
              <polygon points="15.2,0 0,19.5 8.8,22.6 8.8,38 24,17.4 15.2,15.4" />
            </svg>
          ) : (
            <Battery className="w-3.5 h-3.5 text-neutral-400" />
          )}
          <span className={charging ? "text-[#4ade80] font-semibold" : ""}>{batLevel}%</span>
        </div>
      </div>

      {/* Gauges */}
      <div className="space-y-2.5 my-auto">
        {/* CPU */}
        <div>
          <div className="flex justify-between text-[11px] font-mono mb-1">
            <span className="text-neutral-400">CPU</span>
            <span className="text-white font-semibold">{Math.round(cpu)}%</span>
          </div>
          <div className="w-full bg-neutral-800 h-1.5 rounded-full overflow-hidden">
            <div
              className="bg-white/80 h-full rounded-full transition-all duration-500 ease-out"
              style={{ width: `${Math.min(100, Math.max(0, cpu))}%` }}
            />
          </div>
        </div>

        {/* RAM */}
        <div>
          <div className="flex justify-between text-[11px] font-mono mb-1">
            <span className="text-neutral-400 flex items-center gap-1">
              <HardDrive className="w-2.5 h-2.5" /> RAM
            </span>
            <span className="text-white font-semibold">{Math.round(ram)}%</span>
          </div>
          <div className="w-full bg-neutral-800 h-1.5 rounded-full overflow-hidden">
            <div
              className="bg-white/80 h-full rounded-full transition-all duration-500 ease-out"
              style={{ width: `${Math.min(100, Math.max(0, ram))}%` }}
            />
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between text-[10px] text-neutral-500 font-mono">
        <span>NOMINAL</span>
        <span className="flex items-center gap-1">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          LIVE
        </span>
      </div>
    </div>
  );
};
