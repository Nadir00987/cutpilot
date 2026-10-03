import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "var(--bg)",
        panel: "var(--card)",
        raise: "var(--surface)",
        wash: "var(--muted-bg)",
        line: "var(--border)",
        fog: "var(--muted-fg)",
        snow: "var(--fg)",
        brand: "var(--accent)",
        branddeep: "var(--accent-deep)",
        royal: "var(--secondary)",
        ok: "var(--success)",
        warn: "var(--warning)",
        bad: "var(--destructive)",
      },
      fontFamily: {
        display: ["var(--font-display)", "sans-serif"],
        body: ["var(--font-body)", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 24px rgba(225,29,72,0.35)",
      },
    },
  },
  plugins: [],
};
export default config;
