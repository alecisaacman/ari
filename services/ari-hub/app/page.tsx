import { ACEConsole } from "@/src/components/ace/ace-console";
import { getHealthSnapshot } from "@/src/core/api/services";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const health = await getHealthSnapshot();
  return <ACEConsole initialHealth={health} />;
}
