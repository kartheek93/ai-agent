/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "Segoe UI", "Helvetica Neue", "sans-serif"],
        display: ["Space Grotesk", "Inter", "Segoe UI", "sans-serif"],
        mono: ["JetBrains Mono", "Cascadia Code", "Consolas", "monospace"],
      },
      colors: {
        brand: {
          50:  "#eff6ff",
          100: "#dbeafe",
          200: "#bfdbfe",
          300: "#93c5fd",
          400: "#63b3ed",
          500: "#3b82f6",
          600: "#2563eb",
          700: "#1d4ed8",
          800: "#1e3a8a",
          900: "#1e3a6a",
        },
        surface: {
          base:   "#050a14",
          panel:  "rgba(10, 15, 30, 0.75)",
          input:  "rgba(255,255,255,0.04)",
        },
      },
      boxShadow: {
        panel: "0 4px 32px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.06)",
        glow:  "0 0 32px rgba(99,179,237,0.2)",
        "glow-lg": "0 0 64px rgba(59,130,246,0.25)",
        "blue-glow": "0 4px 20px rgba(59,130,246,0.35)",
      },
      animation: {
        "fade-in":     "fadeIn 0.5s ease both",
        "fade-slide":  "fadeSlideUp 0.55s cubic-bezier(0.16,1,0.3,1) both",
        shimmer:       "shimmer 1.8s infinite linear",
        "pulse-glow":  "pulseGlow 2.5s ease-in-out infinite",
        scanline:      "scanline 6s linear infinite",
        float:         "float 4s ease-in-out infinite",
        "spin-slow":   "spin 12s linear infinite",
      },
      keyframes: {
        fadeIn: {
          "0%":   { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        fadeSlideUp: {
          "0%":   { opacity: "0", transform: "translateY(20px) scale(0.98)" },
          "100%": { opacity: "1", transform: "translateY(0) scale(1)" },
        },
        shimmer: {
          "0%":   { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition:  "200% 0" },
        },
        pulseGlow: {
          "0%, 100%": { boxShadow: "0 0 12px rgba(99,179,237,0.15)" },
          "50%":      { boxShadow: "0 0 28px rgba(99,179,237,0.4)"  },
        },
        scanline: {
          "0%":   { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(100vh)"  },
        },
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%":      { transform: "translateY(-8px)" },
        },
      },
      backdropBlur: {
        xs: "4px",
      },
    },
  },
  plugins: [],
};
