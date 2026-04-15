import { ACE_FULL_NAME, ARI_FULL_NAME } from "@/src/core/identity";
import { LoginForm } from "@/src/components/ace/login-form";

export default function LoginPage() {
  return (
    <main className="login-shell">
      <section className="login-panel">
        <p className="eyebrow">{ACE_FULL_NAME}</p>
        <h1>ARI</h1>
        <p className="login-copy">
          {ARI_FULL_NAME}. This private ACE interface opens the ARI runtime from browser, phone, and other personal access surfaces.
        </p>
        <LoginForm />
      </section>
    </main>
  );
}
