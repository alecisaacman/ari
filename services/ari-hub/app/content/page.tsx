import { redirect } from "next/navigation";

import { Content } from "@/src/components/hub/content";
import { HubTop } from "@/src/components/hub/top";
import { TouchIdButton } from "@/src/components/hub/touch-id";
import { getUiSession } from "@/src/core/auth/guard";
import { hasPasskeys } from "@/src/core/auth/passkeys";
import { getContentLibrary } from "@/src/core/ari-spine/brain-bridge";

export const dynamic = "force-dynamic";

// Content: its own page, apart from the hub's day-to-day. Every piece of content and
// where it is in the content process. Creator only.
export default async function ContentRoute() {
  const session = await getUiSession();
  if (!session) {
    redirect("/login");
  }
  const creator = session.role === "creator";

  return (
    <main className="hub hub-wide">
      <HubTop active="content" creator={creator} />
      {creator ? (
        <ContentLoader />
      ) : (
        <section className="hub-panel hub-locked">
          <h2>Content is for its creator</h2>
          <p className="hub-quiet">
            {hasPasskeys()
              ? "Unlock with Touch ID to see and move ARI's content."
              : "Set up Touch ID once on this Mac. After that, Touch ID unlocks this side and the password only opens Today."}
          </p>
          <TouchIdButton mode={hasPasskeys() ? "unlock" : "setup"} />
        </section>
      )}
    </main>
  );
}

async function ContentLoader() {
  try {
    return <Content library={await getContentLibrary()} />;
  } catch (error) {
    return (
      <section className="hub-panel hub-down">
        <h2>The content library didn&apos;t load</h2>
        <p className="hub-quiet">{error instanceof Error ? error.message : "ARI didn't answer."}</p>
      </section>
    );
  }
}
