import { LoginForm } from "@/src/components/ace/login-form";
import { TouchIdButton } from "@/src/components/hub/touch-id";
import { hasPasskeys } from "@/src/core/auth/passkeys";

export const dynamic = "force-dynamic";

export default function LoginPage() {
  const touchId = hasPasskeys();
  return (
    <main className="login-shell">
      <section className="login-panel">
        <h1>ARI</h1>
        <p className="login-copy">
          {touchId ? "Touch ID opens everything. The password opens Today." : "Sign in to talk to ARI and see your day."}
        </p>
        {touchId ? <TouchIdButton mode="unlock" /> : null}
        <LoginForm />
      </section>
    </main>
  );
}
