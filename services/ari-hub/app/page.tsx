import { ACEConsole } from "@/src/components/ace/ace-console";
import { getHealthSnapshot } from "@/src/core/api/services";

export default async function HomePage() {
  const health = await getHealthSnapshot();
  return <ACEConsole initialHealth={health} />;
}
