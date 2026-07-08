import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  // 홈 디렉터리의 잘못된 lockfile 때문에 워크스페이스 루트가 틀리게 추론되는 것 방지
  turbopack: {
    root: path.join(process.cwd()),
  },
};

export default nextConfig;
