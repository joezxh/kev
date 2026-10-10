// Re-export the legacy /console/scenarios page from the studio route so
// the lifecycle shell has a real (not placeholder) ch1 surface today.
// When the studio-specific ch1 implementation lands (per Wave C-2-1), this
// thin re-export will be deleted and replaced with a studio-native page
// that uses the same /api/console/scenario-* contracts.
import ScenariosPage from "@/app/console/scenarios/page";

export default function StudioDomainsPage() {
  return <ScenariosPage />;
}
