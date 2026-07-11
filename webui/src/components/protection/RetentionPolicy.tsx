/**
 * RetentionPolicy Component
 * ==========================
 * Displays snapshot retention policies with daily, weekly, and monthly keep counts.
 */

import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";

export interface RetentionPolicyItem {
  name: string;
  keepDaily: number;
  keepWeekly: number;
  keepMonthly: number;
}

interface RetentionPolicyProps {
  policies: RetentionPolicyItem[];
}

export function RetentionPolicy({ policies }: RetentionPolicyProps) {
  if (policies.length === 0) {
    return (
      <p className="text-sm text-mk-text-muted p-4">No retention policies defined.</p>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Policy Name</TableHead>
          <TableHead>Keep Daily</TableHead>
          <TableHead>Keep Weekly</TableHead>
          <TableHead>Keep Monthly</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {policies.map((policy) => (
          <TableRow key={policy.name}>
            <TableCell className="font-medium text-mk-text-primary">
              {policy.name}
            </TableCell>
            <TableCell>{policy.keepDaily}</TableCell>
            <TableCell>{policy.keepWeekly}</TableCell>
            <TableCell>{policy.keepMonthly}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
