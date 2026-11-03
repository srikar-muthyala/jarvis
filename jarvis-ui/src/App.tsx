import React, { useState, useRef, useEffect } from "react";
import { motion } from "framer-motion";
import {
  Mic,
  MicOff,
  Send,
  VolumeX,
  ChevronDown,
  ChevronUp,
  Sparkles,
  ExternalLink,
  X,
  Wifi,
  WifiOff,
} from "lucide-react";
import { useJarvis } from "./hooks/useJarvis";
import { RoboMascot } from "./components/RoboMascot";
import { ClockCard } from "./components/ClockCard";
import { StatsCard } from "./components/StatsCard";

export default function App() {
  const {
    state,
    sendQuery,
    toggleMic,
    stopSpeech,
    respondApproval,
    setExpanded,
  } = useJarvis();

  const [inputVal, setInputVal] = useState("");
  const replyScrollRef = useRef<HTMLDivElement>(null);

  // Auto scroll response bubble on update
  useEffect(() => {
    if (replyScrollRef.current) {
      replyScrollRef.current.scrollTop = replyScrollRef.current.scrollHeight;
    }
  }, [state.lastReply]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputVal.trim()) return;
    sendQuery(inputVal.trim());
    setInputVal("");
    if (!state.expanded) {
      setExpanded(true);
    }
  };

  const isLinkPrompt =
    state.hasApproval ||
    state.lastReply.toLowerCase().includes("would you like me to open that link") ||
    state.lastReply.toLowerCase().includes("open that link for you");

  return (
    <div className="w-full h-screen flex flex-col items-center justify-start pt-3 px-4 bg-transparent select-none font-sans antialiased">
      <motion.div
        layout
        transition={{ type: "spring", stiffness: 420, damping: 32 }}
        className={`bg-[#0c0c0e]/95 backdrop-blur-2xl border border-white/10 shadow-2xl text-white overflow-hidden transition-all ${
          state.expanded ? "w-full max-w-[500px] rounded-3xl p-4" : "w-[330px] rounded-full py-2 px-3.5"
        }`}
        style={{
          boxShadow: "0 20px 50px rgba(0, 0, 0, 0.7), 0 0 0 1px rgba(255, 255, 255, 0.08)",
        }}
      >
        {/* COLLAPSED NOTCH VIEW */}
        {!state.expanded ? (
          <div className="flex items-center justify-between gap-3 h-8 pywebview-drag-region" data-tauri-drag-region>
            <div
              className="flex items-center gap-2.5 cursor-pointer flex-1"
              onClick={() => setExpanded(true)}
            >
              <RoboMascot mood={state.mood} size={28} />
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold tracking-wider font-mono uppercase text-white/90">
                  JARVIS
                </span>
                <span
                  className="w-1.5 h-1.5 rounded-full"
                  style={{ backgroundColor: state.statusColor }}
                />
                <span className="text-[11px] font-medium text-neutral-400 capitalize">
                  {state.statusLabel}
                </span>
              </div>
            </div>

            {/* Quick action buttons */}
            <div className="flex items-center gap-1.5">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  toggleMic();
                }}
                className={`p-1.5 rounded-full transition-colors ${
                  state.isListening
                    ? "bg-red-500/20 text-red-400 border border-red-500/30 animate-pulse"
                    : "bg-white/5 hover:bg-white/10 text-neutral-300"
                }`}
                title={state.isListening ? "Listening..." : "Click to speak"}
              >
                {state.isListening ? <Mic className="w-3.5 h-3.5" /> : <MicOff className="w-3.5 h-3.5 text-neutral-400" />}
              </button>

              <button
                onClick={() => setExpanded(true)}
                className="p-1 rounded-full bg-white/5 hover:bg-white/10 text-neutral-400 hover:text-white transition-colors"
                title="Expand TwoCode Island"
              >
                <ChevronDown className="w-4 h-4" />
              </button>
            </div>
          </div>
        ) : (
          /* EXPANDED TWOCODE DASHBOARD */
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2 }}
            className="flex flex-col gap-3.5"
          >
            {/* Header bar */}
            <div className="flex items-center justify-between pb-2 border-b border-white/5 pywebview-drag-region" data-tauri-drag-region>
              <div className="flex items-center gap-2.5">
                <RoboMascot mood={state.mood} size={34} />
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold tracking-widest uppercase font-mono text-white">
                      JARVIS AI
                    </span>
                    <span
                      className="px-2 py-0.5 rounded-full text-[9px] font-mono font-medium tracking-wide border uppercase"
                      style={{
                        borderColor: `${state.statusColor}40`,
                        color: state.statusColor,
                        backgroundColor: `${state.statusColor}15`,
                      }}
                    >
                      {state.statusLabel}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 text-[10px] text-neutral-500 mt-0.5">
                    {state.connected ? (
                      <span className="flex items-center gap-1 text-emerald-400/90 font-mono">
                        <Wifi className="w-2.5 h-2.5" /> ONLINE
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-neutral-500 font-mono">
                        <WifiOff className="w-2.5 h-2.5" /> STANDALONE
                      </span>
                    )}
                    <span>•</span>
                    <span className="font-mono">GEMINI 3.1 FL</span>
                  </div>
                </div>
              </div>

              {/* Controls */}
              <div className="flex items-center gap-1.5">
                {state.isSpeaking && (
                  <button
                    onClick={stopSpeech}
                    className="p-1.5 rounded-xl bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/30 transition-all flex items-center gap-1 text-xs px-2.5"
                    title="Stop Jarvis voice playback"
                  >
                    <VolumeX className="w-3.5 h-3.5 animate-pulse" />
                    <span className="text-[11px] font-medium">Mute</span>
                  </button>
                )}

                <button
                  onClick={toggleMic}
                  className={`p-1.5 rounded-xl transition-all flex items-center gap-1 text-xs px-2.5 ${
                    state.isListening
                      ? "bg-red-500/20 text-red-300 border border-red-500/40 animate-pulse"
                      : "bg-white/5 hover:bg-white/10 text-neutral-300 border border-white/5"
                  }`}
                  title="Voice Command"
                >
                  <Mic className="w-3.5 h-3.5" />
                  <span className="text-[11px] font-medium">
                    {state.isListening ? "Listening" : "Mic"}
                  </span>
                </button>

                <button
                  onClick={() => setExpanded(false)}
                  className="p-1.5 rounded-xl bg-white/5 hover:bg-white/10 text-neutral-400 hover:text-white transition-colors border border-white/5"
                  title="Collapse"
                >
                  <ChevronUp className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Conversation Viewport */}
            <div className="bg-[#141416] border border-white/5 rounded-2xl p-3 flex flex-col gap-2">
              {state.lastQuery && (
                <div className="flex items-start gap-2 text-xs text-neutral-400 border-b border-white/5 pb-2">
                  <span className="font-mono text-[10px] uppercase text-neutral-500 mt-0.5">
                    YOU:
                  </span>
                  <span className="text-neutral-300 italic font-medium">
                    "{state.lastQuery}"
                  </span>
                </div>
              )}

              {/* Scrollable Response Text */}
              <div
                ref={replyScrollRef}
                className="max-h-28 overflow-y-auto custom-scrollbar text-[13px] leading-relaxed text-neutral-200 select-text pr-1 font-sans"
              >
                {state.lastReply}
              </div>

              {/* Action Buttons: If Jarvis asks to open a link */}
              {isLinkPrompt && (
                <motion.div
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="mt-1 pt-2 border-t border-white/10 flex items-center justify-end gap-2"
                >
                  <button
                    onClick={() => respondApproval(false)}
                    className="flex items-center gap-1 px-3 py-1.5 rounded-xl text-xs font-medium bg-neutral-800 hover:bg-neutral-700 text-neutral-300 border border-white/5 transition-colors"
                  >
                    <X className="w-3.5 h-3.5" />
                    <span>No, cancel</span>
                  </button>
                  <button
                    onClick={() => respondApproval(true)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-emerald-500 hover:bg-emerald-400 text-black shadow-lg shadow-emerald-500/20 transition-all hover:scale-[1.02]"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                    <span>Yes, open link</span>
                  </button>
                </motion.div>
              )}
            </div>

            {/* TwoCode Widgets 2-Column Grid */}
            <div className="grid grid-cols-2 gap-3 h-28">
              <ClockCard />
              <StatsCard telemetry={state.telemetry} />
            </div>

            {/* Quick Query Bar */}
            <form onSubmit={handleSubmit} className="relative flex items-center">
              <div className="absolute left-3 text-neutral-500">
                <Sparkles className="w-3.5 h-3.5" />
              </div>
              <input
                type="text"
                value={inputVal}
                onChange={(e) => setInputVal(e.target.value)}
                placeholder="Ask Jarvis anything..."
                className="w-full bg-[#171717] hover:bg-[#1a1a1a] focus:bg-[#1a1a1a] border border-white/10 focus:border-white/20 rounded-2xl pl-9 pr-10 py-2.5 text-xs text-white placeholder-neutral-500 focus:outline-none transition-colors"
              />
              <button
                type="submit"
                disabled={!inputVal.trim()}
                className="absolute right-2 p-1.5 rounded-xl bg-white/10 hover:bg-white text-neutral-300 hover:text-black transition-all disabled:opacity-30 disabled:hover:bg-white/10 disabled:hover:text-neutral-300"
              >
                <Send className="w-3.5 h-3.5" />
              </button>
            </form>
          </motion.div>
        )}
      </motion.div>
    </div>
  );
}
