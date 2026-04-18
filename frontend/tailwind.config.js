/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        level: {
          atencao: "#3b82f6",
          alerta: "#eab308",
          em1: "#f97316",
          em2: "#ef4444",
        },
      },
    },
  },
  plugins: [],
};
