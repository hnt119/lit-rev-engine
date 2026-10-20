import type { NextConfig } from "next";
import path from "node:path";
const config: NextConfig = {
  agentRules: false,
  turbopack: {root:path.resolve(process.cwd(),"../..")},
  poweredByHeader: false,
  devIndicators: false,
  allowedDevOrigins: ["127.0.0.1"],
  async headers() { return [{source:"/:path*",headers:[
    {key:"X-Content-Type-Options",value:"nosniff"},
    {key:"Referrer-Policy",value:"same-origin"},
    {key:"Cache-Control",value:"no-store"}
  ]}]; }
};
export default config;
