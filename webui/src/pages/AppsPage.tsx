/**
 * AppsPage
 * =========
 * Containers, stacks, and VMs in one unified view.
 */

import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ContainerTable } from "@/components/apps/ContainerTable";
import { StackCard } from "@/components/apps/StackCard";
import { VMTable } from "@/components/apps/VMTable";

export function AppsPage() {
  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-mk-text-primary">Apps</h1>
        <Button size="sm">
          <Plus size={14} />
          Deploy Container
        </Button>
      </div>

      <Tabs defaultValue="containers">
        <TabsList>
          <TabsTrigger value="containers">Containers</TabsTrigger>
          <TabsTrigger value="stacks">Stacks</TabsTrigger>
          <TabsTrigger value="vms">VMs</TabsTrigger>
        </TabsList>

        <TabsContent value="containers">
          <ContainerTable />
        </TabsContent>

        <TabsContent value="stacks">
          <StackCard />
        </TabsContent>

        <TabsContent value="vms">
          <VMTable />
        </TabsContent>
      </Tabs>
    </div>
  );
}
