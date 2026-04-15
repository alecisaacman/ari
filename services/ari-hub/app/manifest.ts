import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "ARI",
    short_name: "ARI",
    description: "Private operator hub for ARI.",
    start_url: "/",
    display: "standalone",
    background_color: "#efeee9",
    theme_color: "#efeee9",
    icons: [
      {
        src: "/icon.svg",
        sizes: "any",
        type: "image/svg+xml"
      }
    ]
  };
}
