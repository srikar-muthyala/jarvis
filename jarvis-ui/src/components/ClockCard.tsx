import React, { useState, useEffect } from "react";
import { Clock } from "lucide-react";

export const ClockCard: React.FC = () => {
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const hours = time.toLocaleTimeString([], { hour: "2-digit", hour12: false });
  const minutes = time.toLocaleTimeString([], { minute: "2-digit" });
  const seconds = time.getSeconds();
  const dateStr = time.toLocaleDateString([], {
    weekday: "short",
    month: "short",
    day: "numeric",
  });

  return (
    <div className="flex flex-col justify-between p-3.5 bg-[#171717] hover:bg-[#1a1a1a] transition-colors rounded-2xl border border-white/5 select-none h-full">
      <div className="flex items-center justify-between text-xs text-neutral-400">
        <span className="flex items-center gap-1.5 font-medium tracking-wide uppercase text-[11px] text-neutral-400">
          <Clock className="w-3.5 h-3.5 text-neutral-500" /> Time
        </span>
        <span className="text-[11px] font-mono text-neutral-500">{dateStr}</span>
      </div>

      <div className="my-auto py-1 flex items-baseline justify-center gap-1">
        <span className="text-3xl font-bold tracking-tight text-white font-mono">
          {hours}
        </span>
        <span
          className="text-2xl font-bold font-mono text-neutral-400 transition-opacity duration-300"
          style={{ opacity: seconds % 2 === 0 ? 1 : 0.25 }}
        >
          :
        </span>
        <span className="text-3xl font-bold tracking-tight text-white font-mono">
          {minutes}
        </span>
      </div>

      <div className="flex items-center justify-between text-[11px] text-neutral-500 font-mono">
        <span>UTC+5:30</span>
        <span className="text-[10px] uppercase tracking-wider text-neutral-400 bg-white/5 px-1.5 py-0.5 rounded">
          Sync
        </span>
      </div>
    </div>
  );
};
