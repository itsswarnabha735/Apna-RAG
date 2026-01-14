import { NextRequest, NextResponse } from 'next/server';
import { GoogleGenAI } from "@google/genai";

// --- Configuration ---
// IMPORTANT: Set these in your Vercel Environment Variables
const TUNNEL_URL = process.env.TUNNEL_URL || "http://localhost:8000";
const GEMINI_API_KEY = process.env.GEMINI_API_KEY || "";

interface SearchResult {
    text: string;
    score: number;
    source: string;
}

interface SearchResponse {
    results: SearchResult[];
    query: string;
}

export async function POST(request: NextRequest) {
    try {
        const { message } = await request.json();

        if (!message) {
            return NextResponse.json({ error: "Message is required" }, { status: 400 });
        }

        // Step 1: Fetch context from Local RAG Agent
        let context = "";
        let sources: string[] = [];

        try {
            const searchResponse = await fetch(`${TUNNEL_URL}/search`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: message, top_k: 5 }),
            });

            if (searchResponse.ok) {
                const searchData: SearchResponse = await searchResponse.json();
                context = searchData.results.map(r => r.text).join("\n\n---\n\n");
                sources = searchData.results.map(r => r.source);
            } else {
                console.warn("Local RAG agent returned error:", searchResponse.status);
            }
        } catch (fetchError) {
            console.warn("Could not reach local RAG agent:", fetchError);
            // Continue anyway - answer without context
        }

        // Step 2: Call Gemini Flash
        if (!GEMINI_API_KEY) {
            return NextResponse.json({
                error: "Gemini API key not configured. Set GEMINI_API_KEY in environment."
            }, { status: 500 });
        }

        const genAI = new GoogleGenAI({ apiKey: GEMINI_API_KEY });

        const systemPrompt = `You are a helpful AI assistant with access to the user's personal knowledge base.
Answer questions using the provided context. If the context doesn't contain relevant information, 
say so and provide a general answer based on your training.

Context from Knowledge Base:
${context || "No context available from local knowledge base."}`;

        const response = await genAI.models.generateContent({
            model: "gemini-2.0-flash",
            contents: [
                { role: "user", parts: [{ text: systemPrompt + "\n\nUser Question: " + message }] }
            ],
        });

        const answer = response.text || "I couldn't generate a response.";

        return NextResponse.json({
            answer,
            sources: sources.length > 0 ? sources : undefined,
            hasContext: context.length > 0,
        });

    } catch (error) {
        console.error("Chat API error:", error);
        return NextResponse.json({
            error: "An error occurred while processing your request."
        }, { status: 500 });
    }
}
