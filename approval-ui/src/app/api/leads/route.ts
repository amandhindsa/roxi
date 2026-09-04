import { NextRequest, NextResponse } from "next/server";

const ROXI_API = process.env.ROXI_API_URL || "http://localhost:8080";

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const vertical = searchParams.get("vertical") || "hauler_ai";
  const status = searchParams.get("status") || "pending";
  const limit = searchParams.get("limit") || "50";

  const res = await fetch(
    `${ROXI_API}/api/leads?vertical=${vertical}&status=${status}&limit=${limit}`,
    { cache: "no-store" }
  );

  if (!res.ok) {
    return NextResponse.json({ error: "upstream error" }, { status: res.status });
  }

  const data = await res.json();
  return NextResponse.json(data);
}
