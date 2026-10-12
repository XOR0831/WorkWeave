import coreWebVitals from "eslint-config-next/core-web-vitals";
import typescript from "eslint-config-next/typescript";

const config = [
  ...coreWebVitals,
  ...typescript,
  { ignores: [".next/**", "out/**", "out-http/**", "playwright-report/**", "test-results/**", "next-env.d.ts"] },
];

export default config;
