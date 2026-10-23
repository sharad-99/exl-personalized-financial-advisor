"use client";

import { useParams } from "next/navigation";

import { CustomerProfile } from "@/components/customers/customer-profile";
import { EmptyState } from "@/components/shared/ui";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default function CustomerProfilePage() {
  const { customerId } = useParams<{ customerId: string }>();
  if (!UUID.test(customerId)) return <EmptyState title="Customer not found" />;
  // The backend decides access: a customer requesting someone else's ID gets 404.
  return <CustomerProfile customerId={customerId} />;
}
