const path = require("node:path");
const distDirFromEnv = process.env.NEXT_DIST_DIR?.trim();

/** @type {import('next').NextConfig} */
module.exports = {
  reactStrictMode: true,
  distDir: distDirFromEnv || undefined,
  experimental: {
    externalDir: true,
  },
  turbopack: {
    root: path.join(__dirname, "../.."),
  },
};
