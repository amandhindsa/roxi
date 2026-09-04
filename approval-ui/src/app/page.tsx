import { LeadList } from "@/components/LeadList";

export const revalidate = 0;

export default function Home({
  searchParams,
}: {
  searchParams: { status?: string; vertical?: string };
}) {
  const status = searchParams.status || "pending";
  const vertical = searchParams.vertical || process.env.NEXT_PUBLIC_VERTICAL || "hauler_ai";

  const statuses = ["pending", "approved", "rejected", "sent", "replied"];

  return (
    <div>
      <div className="flex items-baseline justify-between mb-6">
        <div>
          <h1 className="text-2xl font-medium tracking-tight">{vertical.replace(/_/g, " ")}</h1>
          <p className="text-ink-soft text-sm font-mono mt-1">
            Leads that matched ICP — approve to queue for send
          </p>
        </div>
        <a
          href="/api/stats"
          className="text-xs font-mono text-ink-soft border border-rule px-3 py-1.5 hover:border-ink transition-colors"
        >
          stats
        </a>
      </div>

      {/* Status tabs */}
      <div className="flex gap-1 mb-6 border-b border-rule">
        {statuses.map((s) => (
          <a
            key={s}
            href={`?status=${s}&vertical=${vertical}`}
            className={`px-3 py-2 text-sm font-mono -mb-px border-b-2 transition-colors ${
              s === status
                ? "border-ink text-ink"
                : "border-transparent text-ink-soft hover:text-ink"
            }`}
          >
            {s}
          </a>
        ))}
      </div>

      <LeadList status={status} vertical={vertical} />
    </div>
  );
}
