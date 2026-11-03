/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        obsidian: {
          950: "#080808",
          900: "#0f0f0f",
          850: "#141414",
          800: "#1a1a1a",
          700: "#262626",
          600: "#333333",
        },
      },
      animation: {
        "pulse-subtle": "pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "breathing": "breathe 3s ease-in-out infinite",
      },
      keyframes: {
        breathe: {
          "0%, 100%": { opacity: "0.4", transform: "scale(0.98)" },
          "50%": { opacity: "1", transform: "scale(1.02)" },
        },
      },
    },
  },
  plugins: [],
}
