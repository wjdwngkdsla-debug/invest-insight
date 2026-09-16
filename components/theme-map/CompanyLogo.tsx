"use client";

import Image from "next/image";
import { useState } from "react";
import { companyLogos as logos, companyPlaceholder } from "@/lib/company-logos";

export function CompanyLogo({ id, name, size = 28, className = "" }: {
  id: string; name: string; size?: number; className?: string;
}) {
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const src = logos[id]?.src;
  return <span className={`company-logo ${className}`} title={name} data-fallback={!src || failedSrc === src} data-tone={logos[id]?.background}
    style={{ width: size, height: size, backgroundColor: src && failedSrc !== src ? logos[id]?.canvasColor : undefined }} aria-hidden="true">
    {src && failedSrc !== src
      ? <Image src={src} alt="" width={size} height={size} unoptimized draggable={false}
          onError={() => setFailedSrc(src)} />
      : <Image src={companyPlaceholder} alt="" width={size} height={size} unoptimized draggable={false} />}
  </span>;
}

export function CompanyIdentity({ id, name, size = 26 }: { id: string; name: string; size?: number }) {
  return <span className="company-identity"><CompanyLogo key={id} id={id} name={name} size={size} /><span>{name}</span></span>;
}
