import { NextRequest, NextResponse } from "next/server"
import { uploadFile } from "@/lib/storage/r2"
import { createDb } from "@/lib/db"
import { updateSession } from "@/lib/db/queries"

// Maximum file size: 5MB
const MAX_FILE_SIZE = 5 * 1024 * 1024

function getDb(req: NextRequest) {
  const d1 = (req as unknown as { env?: { DB?: D1Database } }).env?.DB
  return createDb(d1)
}

export async function POST(req: NextRequest) {
  const bucket = (req as unknown as { env?: { BUCKET?: R2Bucket } }).env?.BUCKET
  const formData = await req.formData()
  const sessionId = formData.get("sessionId") as string
  const file = formData.get("file") as File | null

  if (!sessionId || !file) {
    return NextResponse.json(
      { error: "sessionId and file are required" },
      { status: 400 },
    )
  }

  // Check file size
  if (file.size > MAX_FILE_SIZE) {
    return NextResponse.json(
      { error: `File size exceeds maximum of ${MAX_FILE_SIZE / 1024 / 1024}MB` },
      { status: 413 },
    )
  }

  // Check file type
  const allowedExtensions = [".json", ".md", ".txt"]
  const hasAllowedExtension = allowedExtensions.some(ext => file.name.endsWith(ext))
  if (!hasAllowedExtension) {
    return NextResponse.json(
      { error: "Unsupported file format. Please upload .json, .md, or .txt" },
      { status: 400 },
    )
  }

  const buffer = await file.arrayBuffer()

  // Upload to R2 if available (optional in local dev)
  if (bucket) {
    await uploadFile(bucket, sessionId, file.name, buffer)
  }

  // Parse file content
  const text = new TextDecoder().decode(buffer)
  let resumeJson: Record<string, unknown> | null = null

  // Try JSON Resume format first
  if (file.name.endsWith(".json")) {
    try {
      resumeJson = JSON.parse(text)
    } catch {
      return NextResponse.json(
        { error: "Invalid JSON format" },
        { status: 400 },
      )
    }
  } else if (file.name.endsWith(".md") || file.name.endsWith(".txt")) {
    // For markdown/text, store as-is in a simple structure
    // LLM will interpret and structure it via updateSection tool
    resumeJson = {
      basics: { name: "Uploaded Resume" },
      rawContent: text,
    }
  }

  // Update session with parsed resume
  const db = getDb(req)
  await updateSession(db, sessionId, {
    resumeJson: JSON.stringify(resumeJson),
  })

  return NextResponse.json(
    {
      filename: file.name,
      sessionId,
      resumeJson,
    },
    { status: 201 }
  )
}
