import { NextResponse } from 'next/server';

// --- Configuration ---
const TUNNEL_URL = process.env.TUNNEL_URL || "http://localhost:8000";

interface IngestResponse {
    status: string;
    message: string;
    documents_processed?: number;
}

export async function POST() {
    try {
        // Call the local backend's /ingest endpoint
        const response = await fetch(`${TUNNEL_URL}/ingest`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });

        if (!response.ok) {
            const errorText = await response.text();
            console.error("Ingest endpoint error:", errorText);
            return NextResponse.json({
                status: "error",
                message: `Backend returned error: ${response.status}`
            }, { status: response.status });
        }

        const data: IngestResponse = await response.json();
        return NextResponse.json(data);

    } catch (error) {
        console.error("Ingest API error:", error);
        return NextResponse.json({
            status: "error",
            message: "Failed to connect to local backend. Is the tunnel running?"
        }, { status: 503 });
    }
}
