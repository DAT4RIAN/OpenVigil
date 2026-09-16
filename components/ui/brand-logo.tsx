import Image from "next/image";
import styles from "./brand-logo.module.css";

export function BrandLogo({ size = 34 }: { readonly size?: number }) {
  return (
    <Image
      className={styles.logo}
      src="/images/openvigil-logo.png"
      alt="OpenVigil Logo"
      width={size}
      height={size}
      unoptimized
    />
  );
}
