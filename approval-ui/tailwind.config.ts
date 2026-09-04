import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["IBM Plex Sans", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
      colors: {
        ground: "#E9EDF1",
        panel: "#F6F8FA",
        ink: "#14202B",
        "ink-soft": "#4A5A69",
        rule: "#C3CDD6",
        amber: "#B3660C",
        "amber-wash": "#F7EBDA",
        teal: "#106B5E",
        "teal-wash": "#D8EDEB",
      },
    },
  },
  plugins: [],
};

export default config;
