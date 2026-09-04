import { NextRequest, NextResponse } from "next/server";

const ROXI_API = process.env.ROXI_API_URL || "http://localhost:8080";

export async function PATCH(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const body = await req.json();

  const res = await fetch(`${ROXI_API}/api/leads/${params.id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    return NextResponse.json({ error: "upstream error" }, { status: res.status });
  }

  return NextResponse.json(await res.json());
}
