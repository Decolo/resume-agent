import Link from "next/link"

export default function LandingPage() {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center bg-background px-6">
      <main className="flex max-w-2xl flex-col items-center gap-8 text-center">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
          Resume Agent
        </h1>
        <p className="max-w-md text-lg text-muted-foreground">
          AI-powered resume analysis and improvement. Upload your resume, paste
          a job description, and get actionable feedback in seconds.
        </p>
        <div className="flex gap-4">
          <Link
            href="/sessions"
            className="inline-flex h-11 items-center rounded-md bg-primary px-6 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Get Started
          </Link>
          <Link
            href="/settings"
            className="inline-flex h-11 items-center rounded-md border px-6 text-sm font-medium transition-colors hover:bg-accent"
          >
            Settings
          </Link>
        </div>
        <div className="grid gap-4 pt-8 sm:grid-cols-3">
          <div className="rounded-lg border p-4 text-left">
            <h3 className="mb-1 font-semibold">ATS Scoring</h3>
            <p className="text-sm text-muted-foreground">
              Get a detailed ATS compatibility score with actionable suggestions.
            </p>
          </div>
          <div className="rounded-lg border p-4 text-left">
            <h3 className="mb-1 font-semibold">Job Matching</h3>
            <p className="text-sm text-muted-foreground">
              Compare your resume against job descriptions to find keyword gaps.
            </p>
          </div>
          <div className="rounded-lg border p-4 text-left">
            <h3 className="mb-1 font-semibold">AI Rewriting</h3>
            <p className="text-sm text-muted-foreground">
              Let AI improve your bullet points with stronger action verbs and metrics.
            </p>
          </div>
        </div>
      </main>
    </div>
  )
}
