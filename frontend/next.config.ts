import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Silences a Turbopack warning caused by a package-lock.json in the
  // Windows home directory above this project - pins the workspace root to
  // this app instead of letting Next.js infer it upward.
  turbopack: {
    root: path.resolve(__dirname),
  },
};

export default nextConfig;
