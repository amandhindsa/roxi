import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";

const ROXI_API = process.env.ROXI_API_URL || "http://localhost:8080";

function _authHeader(req: NextRequest): Record<string, string> {
  const auth = req.headers.get("authorization");
  return auth ? { authorization: auth } : {};
}

export async function GET(req: NextRequest) {
  // Pass all query params through unchanged
  const search = req.nextUrl.search;
  const res = await fetch(`${ROXI_API}/api/leads${search}`, {
    headers: { ..._authHeader(req), "content-type": "application/json" },
    cache: "no-store",
  });
  if (!res.ok) return NextResponse.json({ error: "upstream error" }, { status: res.status });
  return NextResponse.json(await res.json());
}
