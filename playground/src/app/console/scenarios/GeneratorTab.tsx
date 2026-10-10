"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

export function GeneratorTab({
  scenario,
  spec,
  scenarioId,
  onSave,
}: {
  scenario: string;
  spec: { generator?: unknown; distill?: unknown; routing?: unknown; smoke_probe?: unknown };
  scenarioId: string;
  onSave: (subfields: { generator: unknown; distill: unknown; routing: unknown; smoke_probe: unknown }) => Promise<void>;
}) {
  void scenario; void scenarioId; // surfaced for future Save + preview/dry-run wiring
  const [draft, setDraft] = useState({
    generator: JSON.stringify(spec.generator ?? {}, null, 2),
    distill: JSON.stringify(spec.distill ?? {}, null, 2),
    routing: JSON.stringify(spec.routing ?? {}, null, 2),
    smoke_probe: JSON.stringify(spec.smoke_probe ?? {}, null, 2),
  });
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      const subfields = {
        generator: JSON.parse(draft.generator),
        distill: JSON.parse(draft.distill),
        routing: JSON.parse(draft.routing),
        smoke_probe: JSON.parse(draft.smoke_probe),
      };
      await onSave(subfields);
    } catch (e) {
      // JSON parse error or save error
      console.error(e);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <Tabs defaultValue="generator">
        <TabsList>
          <TabsTrigger value="generator">Generator</TabsTrigger>
          <TabsTrigger value="distill">Distill</TabsTrigger>
          <TabsTrigger value="routing">Routing</TabsTrigger>
          <TabsTrigger value="smoke_probe">Smoke Probe</TabsTrigger>
        </TabsList>
        <TabsContent value="generator">
          <Textarea
            value={draft.generator}
            onChange={(e) => setDraft({ ...draft, generator: e.target.value })}
            rows={20}
          />
        </TabsContent>
        <TabsContent value="distill">
          <Textarea
            value={draft.distill}
            onChange={(e) => setDraft({ ...draft, distill: e.target.value })}
            rows={20}
          />
        </TabsContent>
        <TabsContent value="routing">
          <Textarea
            value={draft.routing}
            onChange={(e) => setDraft({ ...draft, routing: e.target.value })}
            rows={20}
          />
        </TabsContent>
        <TabsContent value="smoke_probe">
          <Textarea
            value={draft.smoke_probe}
            onChange={(e) => setDraft({ ...draft, smoke_probe: e.target.value })}
            rows={20}
          />
        </TabsContent>
      </Tabs>
      <Button onClick={() => void handleSave()} disabled={saving}>
        {saving ? "Saving..." : "Save"}
      </Button>
    </div>
  );
}