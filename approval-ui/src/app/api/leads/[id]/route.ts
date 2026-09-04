import { NextRequest, NextResponse } from "next/server";

const ROXI_API = process.env.ROXI_API_URL || "http://localhost:8080";

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const body = await req.json();

  const res = await fetch(`${ROXI_API}/api/leads/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    return NextResponse.json({ error: "upstream error" }, { status: res.status });
  }

  const result = await res.json();

  if (body.status === "rejected" && body.rejection_reason) {
    await fetch(`${ROXI_API}/api/leads/${id}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ outcome: "rejected", reason: body.rejection_reason, note: body.rejection_note }),
    }).catch(() => {});
  }

  return NextResponse.json(result);
}
