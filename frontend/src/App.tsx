import { FormEvent, useEffect, useState } from "react";
import { createSession, dollarsToCents, getCatalog, getHealth, money, sendMessage } from "./api";
import type { ConverseResponse, Health, Package, Product, Turn } from "./types";

const EXAMPLES = [
  {
    label: "Video editing kit",
    budget: "2500",
    message: "I need a laptop for video editing, a monitor, and a two-year warranty. Budget $2,500.",
  },
  {
    label: "Student setup",
    budget: "1200",
    message: "Student setup: a light laptop, a mouse, and headphones under $1,200.",
  },
  {
    label: "Creator dock",
    budget: "2500",
    message: "Creator laptop with a USB4 dock and financing.",
  },
];

const TOOL_LABELS: Record<string, string> = {
  search_catalog: "catalog search",
  check_compatibility: "compatibility",
  lookup_warranties: "warranty lookup",
  get_financing_offers: "financing offers",
  BundleProposal: "package",
};

export function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [catalog, setCatalog] = useState<Product[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [latest, setLatest] = useState<ConverseResponse | null>(null);
  const [message, setMessage] = useState(EXAMPLES[0].message);
  const [budget, setBudget] = useState(EXAMPLES[0].budget);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getHealth(), getCatalog(), createSession()])
      .then(([healthBody, products, session]) => {
        if (cancelled) {
          return;
        }
        setHealth(healthBody);
        setCatalog(products);
        setSessionId(session.session_id);
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setError(reason instanceof Error ? reason.message : "The API is not reachable.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!sessionId || busy) {
      return;
    }
    const text = message.trim();
    if (!text) {
      setError("Write what you need first.");
      return;
    }
    const cents = dollarsToCents(budget);
    if (budget.trim() && cents === null) {
      setError("Budget should be a dollar amount, or left blank.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await sendMessage(sessionId, text, cents);
      setLatest(result);
      setTurns(result.turns);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "The request failed.");
    } finally {
      setBusy(false);
    }
  }

  const modeLabel =
    health == null ? "Connecting" : health.mode === "offline" ? "Offline stub model" : health.model;

  return (
    <>
      <header className="top">
        <div className="brand">
          <span className="mark" aria-hidden="true">
            K
          </span>
          <div>
            <strong>Kitline</strong>
            <em>Shopping concierge</em>
          </div>
        </div>
        <p className="mode">
          {modeLabel}
          {health ? ` · ${health.catalog_size} synthetic products` : ""}
        </p>
      </header>
      <main className="layout">
        <section className="conversation">
          <div className="transcript" aria-live="polite">
            {turns.length === 0 ? (
              <p className="empty">
                Describe a setup. Kitline searches the catalog, checks compatibility, warranty, and financing, then
                returns one package only after those checks pass in code.
              </p>
            ) : (
              turns.map((turn, index) => (
                <article key={`${turn.created_at}-${index}`} className={turn.role === "user" ? "bubble user" : "bubble assistant"}>
                  <span>{turn.role === "user" ? "You" : "Kitline"}</span>
                  <p>{turn.text}</p>
                </article>
              ))
            )}
          </div>
          <form onSubmit={onSubmit}>
            <label>
              Budget in dollars
              <input
                inputMode="decimal"
                value={budget}
                onChange={(event) => setBudget(event.target.value)}
                placeholder="Optional"
              />
            </label>
            <label className="grow">
              What do you need?
              <textarea
                value={message}
                rows={4}
                onChange={(event) => setMessage(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    event.currentTarget.form?.requestSubmit();
                  }
                }}
              />
            </label>
            <div className="row">
              <div className="chips">
                {EXAMPLES.map((example) => (
                  <button
                    key={example.label}
                    type="button"
                    className="chip"
                    onClick={() => {
                      setMessage(example.message);
                      setBudget(example.budget);
                    }}
                  >
                    {example.label}
                  </button>
                ))}
              </div>
              <button type="submit" className="send" disabled={busy || !sessionId}>
                {busy ? "Checking…" : "Assemble package"}
              </button>
            </div>
            {error ? <p className="error">{error}</p> : null}
          </form>
          <CatalogList products={catalog} />
        </section>
        <PackagePanel response={latest} offline={health?.mode !== "bedrock"} />
      </main>
    </>
  );
}

function PackagePanel({ response, offline }: { response: ConverseResponse | null; offline: boolean }) {
  if (!response || !response.package) {
    return (
      <aside className="panel">
        <h2>Package</h2>
        <p className="empty">
          {response?.status === "unfulfilled"
            ? response.message
            : "The package shows up here after the checks pass. Prices come from the catalog, not from the model."}
        </p>
      </aside>
    );
  }
  return <PackageCard response={response} offline={offline} />;
}

function PackageCard({ response, offline }: { response: ConverseResponse; offline: boolean }) {
  const pkg: Package = response.package as Package;
  const tools = [...new Set(response.tools_used.map((name) => TOOL_LABELS[name] ?? name))];
  const pass =
    response.source === "fallback"
      ? "Simpler package after the draft was rejected"
      : response.attempts === 1
        ? "Accepted on the first pass"
        : `Accepted on attempt ${response.attempts}`;
  return (
    <aside className="panel">
      <p className="eyebrow">{pass}</p>
      <h2>{pkg.title}</h2>
      <p>{pkg.summary}</p>
      <table>
        <thead>
          <tr>
            <th>Item</th>
            <th>Qty</th>
            <th>Price</th>
          </tr>
        </thead>
        <tbody>
          {pkg.lines.map((line) => (
            <tr key={line.sku}>
              <td>
                <strong>{line.name}</strong>
                <small>
                  {line.role} · {line.vendor} · {line.sku}
                </small>
              </td>
              <td>{line.quantity}</td>
              <td>{money(line.line_total_cents)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="total">
        <span>Total</span>
        <strong>{money(pkg.grand_total_cents)}</strong>
      </p>
      {pkg.financing ? (
        <p className="finance">
          {pkg.financing.provider} {pkg.financing.offer_id}: {pkg.financing.apr_percent}% APR for{" "}
          {pkg.financing.term_months} months, {money(pkg.financing.monthly_payment_cents)} a month.
        </p>
      ) : (
        <p className="finance">No financing attached.</p>
      )}
      <ul className="checks">
        {pkg.checks.map((check) => (
          <li key={check.name} className={check.ok ? "ok" : "bad"}>
            <strong>{check.name}</strong>
            <span>{check.detail}</span>
          </li>
        ))}
      </ul>
      <p className="fine">
        {offline ? "Offline model." : "Bedrock model."} Tools: {tools.join(", ") || "none recorded"}. {pkg.rationale}
      </p>
    </aside>
  );
}

function CatalogList({ products }: { products: Product[] }) {
  const groups = new Map<string, Product[]>();
  for (const product of products) {
    const list = groups.get(product.category) ?? [];
    list.push(product);
    groups.set(product.category, list);
  }
  return (
    <details className="catalog">
      <summary>Synthetic catalog ({products.length})</summary>
      {[...groups.entries()].map(([category, items]) => (
        <div key={category}>
          <h3>{category}</h3>
          <ul>
            {items.map((product) => (
              <li key={product.sku}>
                <span>
                  {product.name}
                  <small>
                    {product.vendor} · {product.sku} · {product.stock} in stock
                  </small>
                </span>
                <span>{money(product.price_cents)}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </details>
  );
}
