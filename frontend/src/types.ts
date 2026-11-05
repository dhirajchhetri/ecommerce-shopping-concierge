export type Check = {
  name: string;
  ok: boolean;
  detail: string;
};

export type Line = {
  sku: string;
  name: string;
  vendor: string;
  category: string;
  role: "primary" | "accessory" | "warranty";
  quantity: number;
  unit_price_cents: number;
  line_total_cents: number;
};

export type Financing = {
  offer_id: string;
  provider: string;
  apr_percent: string;
  term_months: number;
  monthly_payment_cents: number;
};

export type Package = {
  title: string;
  summary: string;
  rationale: string;
  lines: Line[];
  grand_total_cents: number;
  financing: Financing | null;
  checks: Check[];
};

export type Turn = {
  role: "user" | "assistant";
  text: string;
  created_at: string;
  package: Package | null;
  status: "validated" | "unfulfilled" | null;
  source: "agent" | "fallback" | null;
  attempts: number | null;
};

export type ConverseResponse = {
  session_id: string;
  status: "validated" | "unfulfilled";
  source: "agent" | "fallback";
  attempts: number;
  message: string;
  package: Package | null;
  tools_used: string[];
  turns: Turn[];
};

export type Product = {
  sku: string;
  name: string;
  vendor: string;
  category: string;
  price_cents: number;
  stock: number;
  description: string;
};

export type Health = {
  status: string;
  mode: string;
  model: string;
  vector_store: string;
  session_store: string;
  catalog_size: number;
};

export type Session = {
  session_id: string;
  created_at: string;
  updated_at: string;
  turns: Turn[];
};
