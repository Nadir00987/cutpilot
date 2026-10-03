/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  // TEMPORARY (tunnel demo only): same-origin API proxy so the browser can
  // reach the API through one public tunnel URL. Revert before packaging.
  async rewrites() {
    return [{ source: "/backend/:path*", destination: "http://localhost:8000/:path*" }];
  },
};
module.exports = nextConfig;
